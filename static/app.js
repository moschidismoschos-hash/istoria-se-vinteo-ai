const story = document.getElementById("story");
const counter = document.getElementById("counter");
const createButton = document.getElementById("createButton");
const progressLine = document.querySelector("#progressLine span");
const progressSteps = [...document.querySelectorAll(".progress-step")];
const statusMessage = document.getElementById("statusMessage");
const toast = document.getElementById("toast");

let toastTimer;

function installScenePanel() {
  if (document.getElementById("sceneDetails")) return;

  const styles = document.createElement("style");
  styles.textContent = `
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
      .scene-details { padding: 12px; }
      .scene-details-head { align-items: stretch; flex-direction: column; }
      .download-video { width: 100%; }
    }
  `;
  document.head.appendChild(styles);

  const panel = document.createElement("section");
  panel.id = "sceneDetails";
  panel.className = "scene-details panel";
  panel.hidden = true;
  panel.innerHTML = `
    <div class="scene-details-head">
      <h2>Περιγραφές σκηνών</h2>
      <a id="downloadVideo" class="download-video" href="#" download hidden>Λήψη δοκιμαστικού βίντεο</a>
    </div>
    <div id="sceneList" class="scene-list"></div>
  `;

  const progressPanel = document.querySelector(".progress-panel");
  progressPanel.insertAdjacentElement("afterend", panel);
}

function updateCounter() {
  counter.textContent = `${story.value.length}/2000`;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 4200);
}

function resetProgress() {
  progressLine.style.width = "0%";
  progressSteps.forEach((step, index) => {
    step.classList.toggle("active", index === 0);
    step.classList.remove("done");
  });
}

function showPreviewVideoProgress() {
  progressSteps.forEach((step) => {
    step.classList.remove("active", "done");
  });
  progressSteps[0].classList.add("done");
  progressSteps[1].classList.add("done");
  progressSteps[2].classList.add("active");
  progressLine.style.width = "66%";
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

  if (!text) {
    story.focus();
    showToast("Γράψε πρώτα την ιστορία σου.");
    return;
  }

  scenePanel.hidden = true;
  downloadVideo.hidden = true;
  createButton.disabled = true;
  createButton.innerHTML = "<span>✦</span><span>Δημιουργία δοκιμαστικού βίντεο…</span>";
  resetProgress();
  statusMessage.textContent = "Η ιστορία χωρίζεται σε σκηνές και δημιουργείται το πρώτο αρχείο βίντεο…";

  try {
    const response = await fetch("/api/dimiourgia", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        story: text,
        style: document.getElementById("style").value,
        duration: document.getElementById("duration").value,
        voice: document.getElementById("voice").value,
        format: document.getElementById("format").value,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.message || "Παρουσιάστηκε πρόβλημα.");
    }

    renderScenes(data.scenes);
    showPreviewVideoProgress();

    if (data.video_url) {
      downloadVideo.href = data.video_url;
      downloadVideo.hidden = false;
      statusMessage.textContent = `${data.message} Το πρώτο δοκιμαστικό βίντεο είναι έτοιμο χωρίς αφήγηση.`;
      showToast("Το δοκιμαστικό βίντεο δημιουργήθηκε.");
    } else {
      statusMessage.textContent = `${data.message} Οι περιγραφές είναι έτοιμες, αλλά το δοκιμαστικό βίντεο δεν δημιουργήθηκε.`;
      showToast(data.video_error || "Δεν δημιουργήθηκε το δοκιμαστικό βίντεο.");
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

installScenePanel();
story.addEventListener("input", updateCounter);
createButton.addEventListener("click", startCreation);
updateCounter();
