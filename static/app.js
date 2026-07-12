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
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3600);
}

function resetProgress() {
  progressLine.style.width = "0%";
  progressSteps.forEach((step, index) => {
    step.classList.toggle("active", index === 0);
    step.classList.remove("done");
  });
}

async function startCreation() {
  const text = story.value.trim();

  if (!text) {
    story.focus();
    showToast("Γράψε πρώτα την ιστορία σου.");
    return;
  }

  createButton.disabled = true;
  createButton.innerHTML = "<span>✦</span><span>Ανάλυση ιστορίας…</span>";
  resetProgress();
  statusMessage.textContent = "Η ιστορία αναλύεται και χωρίζεται σε σκηνές…";

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

    progressSteps[0].classList.remove("active");
    progressSteps[0].classList.add("done");
    progressLine.style.width = "0%";
    statusMessage.textContent = `${data.message} Έτοιμες οι περιγραφές τους.`;
    showToast(data.message);

    console.table(data.scenes);
  } catch (error) {
    statusMessage.textContent = "Η διαδικασία σταμάτησε";
    showToast(error.message);
  } finally {
    createButton.disabled = false;
    createButton.innerHTML = "<span>✦</span><span>Δημιουργία βίντεο</span>";
  }
}

story.addEventListener("input", updateCounter);
createButton.addEventListener("click", startCreation);
updateCounter();
