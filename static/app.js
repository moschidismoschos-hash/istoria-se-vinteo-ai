const story = document.getElementById("story");
const counter = document.getElementById("counter");
const createButton = document.getElementById("createButton");
const progressLine = document.querySelector("#progressLine span");
const progressSteps = [...document.querySelectorAll(".progress-step")];
const statusMessage = document.getElementById("statusMessage");
const toast = document.getElementById("toast");

let toastTimer;

function updateCounter() {
  counter.textContent = `${story.value.length}/2000`;
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
}

function setProgress(stepIndex, message) {
  const percentages = [0, 34, 67, 100];
  progressLine.style.width = `${percentages[stepIndex]}%`;

  progressSteps.forEach((step, index) => {
    step.classList.toggle("active", index === stepIndex);
    step.classList.toggle("done", index < stepIndex);
  });

  statusMessage.textContent = message;
}

function wait(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function startCreation() {
  const text = story.value.trim();

  if (!text) {
    story.focus();
    showToast("Γράψε πρώτα την ιστορία σου.");
    return;
  }

  createButton.disabled = true;
  createButton.innerHTML = "<span>✦</span><span>Δημιουργία…</span>";

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

    setProgress(0, "Δημιουργούνται οι εικόνες των σκηνών…");
    await wait(900);
    setProgress(1, "Οι σκηνές μετατρέπονται σε βίντεο…");
    await wait(900);
    setProgress(2, "Προστίθεται η ελληνική αφήγηση…");
    await wait(900);
    setProgress(3, "Ολοκληρώνεται η τελική εξαγωγή…");
    await wait(800);

    progressSteps.forEach(step => {
      step.classList.remove("active");
      step.classList.add("done");
    });
    progressLine.style.width = "100%";
    statusMessage.textContent = "Η δοκιμαστική διαδικασία ολοκληρώθηκε";
    showToast("Η πρώτη λειτουργική έκδοση δουλεύει σωστά.");
  } catch (error) {
    setProgress(0, "Η διαδικασία σταμάτησε");
    showToast(error.message);
  } finally {
    createButton.disabled = false;
    createButton.innerHTML = "<span>✦</span><span>Δημιουργία βίντεο</span>";
  }
}

story.addEventListener("input", updateCounter);
createButton.addEventListener("click", startCreation);
updateCounter();
