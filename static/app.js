const story = document.getElementById("story");
const counter = document.getElementById("counter");
const createButton = document.getElementById("createButton");
const progressLine = document.querySelector("#progressLine span");
const progressSteps = [...document.querySelectorAll(".progress-step")];
const statusMessage = document.getElementById("statusMessage");
const toast = document.getElementById("toast");

let toastTimer;
let previewObjectUrls = [];

function installPhotoUploader() {
  if (document.getElementById("photoUploader")) return;

  const styles = document.createElement("style");
  styles.textContent = `
    .photo-uploader { margin-top: 12px; padding: 14px; border-radius: 16px; }
    .photo-uploader-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .photo-uploader-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .photo-uploader-icon { display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center; border: 1px solid #315b82; border-radius: 11px; background: rgba(17, 68, 113, .4); color: #71bdff; font-size: 1.15rem; }
    .photo-uploader h2 { margin: 0; font-size: .98rem; }
    .photo-uploader p { margin: 4px 0 0; color: #9db0c5; font-size: .76rem; line-height: 1.35; }
    .photo-picker { display: inline-flex; min-height: 42px; flex: 0 0 auto; align-items: center; justify-content: center; padding: 0 13px; cursor: pointer; border: 1px solid #3f9ee8; border-radius: 11px; background: linear-gradient(145deg, #123d69, #0b2947); color: #dff2ff; font-size: .82rem; font-weight: 800; }
    .photo-picker input { display: none; }
    .photo-selection { margin-top: 10px; color: #7ec4ff; font-size: .78rem; }
    .photo-thumbnails { display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; margin-top: 10px; }
    .photo-thumbnails:empty { display: none; }
    .photo-thumbnails img { display: block; width: 100%; aspect-ratio: 1 / 1; object-fit: cover; border: 1px solid #315a7c; border-radius: 9px; background: #07101a; }
    .scene-details[hidden] { display: none; }
    .scene-details { margin-top: 14px; padding: 15px; border-radius: 16px; }
    .scene-details-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
    .scene-details h2 { margin: 0; font-size: 1rem; }
    .scene-list { display: grid; gap: 9px; }
    .scene-card { padding: 11px 12px; border: 1px solid #29445f; border-radius: 12px; background: rgba(3, 11, 19, .55); }
    .scene-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px; color: #71bdff; font-weight: 800; }
    .scene-card p { margin: 0; color: #e8eef6; font-size: .84rem; line-height: 1.4; }
    .scene-duration { color: #9db0c5; font-size: .76rem; font-weight: 650; white-space: nowrap; }
    .download-video { display: inline-flex; min-height: 40px; align-items: center; justify-content: center; padding: 0 13px; border: 1px solid #4aafff; border-radius: 11px; background: linear-gradient(135deg, #1f9fff, #075bdd); color: white; font-size: .82rem; font-weight: 800; text-decoration: none; }
    .download-video[hidden] { display: none; }
    @media (max-width: 420px) {
      .photo-uploader { padding: 12px; }
      .photo-uploader-head { align-items: stretch; flex-direction: column; }
      .photo-picker { width: 100%; }
      .photo-thumbnails { grid-template-columns: repeat(4, 1fr); }
      .scene-details { padding: 12px; }
      .scene-details-head { align-items: stretch; flex-direction: column; }
      .download-video { width: 100%; }
    }
  `;
  document.head.appendChild(styles);

  const uploader = document.createElement("section");
  uploader.id = "photoUploader";
  uploader.className = "photo-uploader panel";
  uploader.innerHTML = `
    <div class="photo-uploader-head">
      <div class="photo-uploader-title">
        <span class="photo-uploader-icon" aria-hidden="true">▣</span>
        <div>
          <h2>Δικές μου φωτογραφίες</h2>
          <p>Βάλε από 1 έως 20 φωτογραφίες. Αν είναι λιγότερες από τις σκηνές, θα επαναλαμβάνονται.</p>
        </div>
      </div>
      <label class="photo-picker">
        <span>Επιλογή φωτογραφιών</span>
        <input id="photoInput" type="file" accept="image/jpeg,image/png,image/webp" multiple>
      </label>
    </div>
    <div id="photoSelection" class="photo-selection">Δεν επιλέχθηκαν φωτογραφίες — θα χρησιμοποιηθούν οι δοκιμαστικές.</div>
    <div id="photoThumbnails" class="photo-thumbnails"></div>
  `;

  const settings = document.querySelector(".settings");
  settings.insertAdjacentElement("afterend", uploader);

  document.getElementById("photoInput").addEventListener("change", handlePhotoSelection);
}

function installScenePanel() {
  if (document.getElementById("sceneDetails")) return;

  const panel = document.createElement("section");
  panel.id = "sceneDetails";
  panel.className = "scene-details panel";
  panel.hidden = true;
  panel.innerHTML = `
    <div class="scene-details-head">
      <h2>Περιγραφές σκηνών</h2>
      <a id="downloadVideo" class="download-video" href="#" download hidden>Λήψη βίντεο</a>
    </div>
    <div id="sceneList" class="scene-list"></div>
  `;

  const progressPanel = document.querySelector(".progress-panel");
  progressPanel.insertAdjacentElement("afterend", panel);
}

function selectedPhotos() {
  const input = document.getElementById("photoInput");
  return input ? [...input.files] : [];
}

function handlePhotoSelection() {
  const files = selectedPhotos();
  const selection = document.getElementById("photoSelection");
  const thumbnails = document.getElementById("photoThumbnails");

  previewObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  previewObjectUrls = [];
  thumbnails.replaceChildren();

  if (files.length > 20) {
    this.value = "";
    selection.textContent = "Μπορείς να επιλέξεις έως 20 φωτογραφίες.";
    showToast("Μπορείς να επιλέξεις έως 20 φωτογραφίες.");
    return;
  }

  if (!files.length) {
    selection.textContent = "Δεν επιλέχθηκαν φωτογραφίες — θα χρησιμοποιηθούν οι δοκιμαστικές.";
    return;
  }

  selection.textContent = `Επιλέχθηκαν ${files.length} φωτογραφίες.`;

  files.slice(0, 10).forEach((file, index) => {
    const objectUrl = URL.createObjectURL(file);
    previewObjectUrls.push(objectUrl);

    const image = document.createElement("img");
    image.src = objectUrl;
    image.alt = `Επιλεγμένη φωτογραφία ${index + 1}`;
    thumbnails.appendChild(image);
  });

  const previewImages = [...document.querySelectorAll(".preview-grid img")];
  previewImages.forEach((image, index) => {
    const file = files[index % files.length];
    const objectUrl = URL.createObjectURL(file);
    previewObjectUrls.push(objectUrl);
    image.src = objectUrl;
    image.alt = `Δική μου φωτογραφία ${index + 1}`;
  });
}

function updateCounter() {
  counter.textContent = `${story.value.length}/2000`;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 5000);
}

function resetProgress() {
  progressLine.style.width = "0%";
  progressSteps.forEach((step, index) => {
    step.classList.toggle("active", index === 0);
    step.classList.remove("done");
  });
}

function setProgress(completedSteps, activeStep = null) {
  progressSteps.forEach((step, index) => {
    step.classList.remove("active", "done");

    if (index < completedSteps) {
      step.classList.add("done");
    } else if (activeStep === index) {
      step.classList.add("active");
    }
  });

  const percentage = Math.min(100, Math.max(0, completedSteps * 33.33));
  progressLine.style.width = `${percentage}%`;
}

function finishProgress() {
  progressSteps.forEach((step) => {
    step.classList.remove("active");
    step.classList.add("done");
  });
  progressLine.style.width = "100%";
}

function renderScenes(scenes) {
  const panel = document.getElementById("sceneDetails");
  const list = document.getElementById("sceneList");

  list.replaceChildren();

  scenes.forEach((scene) => {
    const card = document.createElement("article");
    card.className = "scene-card";

    const head = document.createElement("div");
    head.className = "scene-card-head";

    const title = document.createElement("span");
    title.textContent = scene.title;

    const duration = document.createElement("span");
    duration.className = "scene-duration";
    duration.textContent = `${scene.duration_seconds} δευτ.`;

    const narration = document.createElement("p");
    narration.textContent = scene.narration;

    head.append(title, duration);
    card.append(head, narration);
    list.appendChild(card);
  });

  panel.hidden = false;
}

async function startCreation() {
  const text = story.value.trim();
  const scenePanel = document.getElementById("sceneDetails");
  const downloadVideo = document.getElementById("downloadVideo");
  const selectedVoice = document.getElementById("voice").value;
  const photos = selectedPhotos();

  if (!text) {
    story.focus();
    showToast("Γράψε πρώτα την ιστορία σου.");
    return;
  }

  if (photos.length > 20) {
    showToast("Μπορείς να επιλέξεις έως 20 φωτογραφίες.");
    return;
  }

  const totalSize = photos.reduce((sum, file) => sum + file.size, 0);
  if (totalSize > 100 * 1024 * 1024) {
    showToast("Οι φωτογραφίες ξεπερνούν συνολικά τα 100 MB.");
    return;
  }

  scenePanel.hidden = true;
  downloadVideo.hidden = true;
  createButton.disabled = true;
  createButton.innerHTML = "<span>✦</span><span>Δημιουργία βίντεο…</span>";
  resetProgress();

  statusMessage.textContent = photos.length
    ? `Χρησιμοποιούνται ${photos.length} δικές σου φωτογραφίες για το βίντεο…`
    : "Χρησιμοποιούνται οι δοκιμαστικές εικόνες για το βίντεο…";

  const formData = new FormData();
  formData.append("story", text);
  formData.append("style", document.getElementById("style").value);
  formData.append("duration", document.getElementById("duration").value);
  formData.append("voice", selectedVoice);
  formData.append("format", document.getElementById("format").value);
  photos.forEach((photo) => formData.append("photos", photo, photo.name));

  try {
    const response = await fetch("/api/dimiourgia", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.message || "Παρουσιάστηκε πρόβλημα.");
    }

    renderScenes(data.scenes);

    const sourceText = data.using_own_photos
      ? `Χρησιμοποιήθηκαν ${data.photo_count} δικές σου φωτογραφίες.`
      : "Χρησιμοποιήθηκαν οι τρεις δοκιμαστικές εικόνες.";

    if (data.video_url) {
      downloadVideo.href = data.video_url;
      downloadVideo.hidden = false;

      if (data.narration_added) {
        downloadVideo.textContent = "Λήψη βίντεο με ελληνική αφήγηση";
        finishProgress();
        statusMessage.textContent = `${sourceText} Το βίντεο είναι έτοιμο με ${data.voice_used.toLowerCase()}.`;
        showToast("Το βίντεο με τις φωτογραφίες σου δημιουργήθηκε.");
      } else if (selectedVoice === "Χωρίς αφήγηση") {
        downloadVideo.textContent = "Λήψη βίντεο χωρίς αφήγηση";
        finishProgress();
        statusMessage.textContent = `${sourceText} Το βίντεο είναι έτοιμο χωρίς αφήγηση.`;
        showToast("Το βίντεο δημιουργήθηκε.");
      } else {
        downloadVideo.textContent = "Λήψη βίντεο χωρίς αφήγηση";
        setProgress(2, 2);
        statusMessage.textContent = `${sourceText} Το βίντεο δημιουργήθηκε, αλλά η αφήγηση απέτυχε.`;
        showToast(data.narration_error || "Δεν δημιουργήθηκε η ελληνική αφήγηση.");
      }
    } else {
      setProgress(1, 1);
      statusMessage.textContent = `${data.message} Το βίντεο δεν δημιουργήθηκε.`;
      showToast(data.video_error || "Δεν δημιουργήθηκε το βίντεο.");
    }

    scenePanel.scrollIntoView({ behavior: "smooth", block: "start" });
    console.table(data.scenes);
  } catch (error) {
    statusMessage.textContent = "Η διαδικασία σταμάτησε";
    showToast(error.message);
  } finally {
    createButton.disabled = false;
    createButton.innerHTML = "<span>✦</span><span>Δημιουργία βίντεο</span>";
  }
}

installPhotoUploader();
installScenePanel();
story.addEventListener("input", updateCounter);
createButton.addEventListener("click", startCreation);
updateCounter();
