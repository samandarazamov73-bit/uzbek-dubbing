// ===========================
// CONFIG
// ===========================
// HuggingFace Space URL — Jarwys/uzbek-dubbing
const API_URL = 'https://jarwys-uzbek-dubbing.hf.space';

// ===========================
// STATE
// ===========================
let selectedFile = null;
let jobId = null;
let pollInterval = null;

// ===========================
// DOM ELEMENTS
// ===========================
const uploadBox     = document.getElementById('uploadBox');
const fileInput     = document.getElementById('fileInput');
const fileSelected  = document.getElementById('fileSelected');
const fileName      = document.getElementById('fileName');
const fileSize      = document.getElementById('fileSize');
const fileRemove    = document.getElementById('fileRemove');
const options       = document.getElementById('options');
const submitBtn     = document.getElementById('submitBtn');
const progressSection = document.getElementById('progressSection');
const progressBar   = document.getElementById('progressBar');
const progressText  = document.getElementById('progressText');
const resultSection = document.getElementById('resultSection');
const resultVideo   = document.getElementById('resultVideo');
const downloadBtn   = document.getElementById('downloadBtn');
const newVideoBtn   = document.getElementById('newVideoBtn');
const errorSection  = document.getElementById('errorSection');
const errorText     = document.getElementById('errorText');
const retryBtn      = document.getElementById('retryBtn');

// ===========================
// UPLOAD BOX — DRAG & DROP
// ===========================
uploadBox.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadBox.classList.add('drag-over');
});

uploadBox.addEventListener('dragleave', () => {
  uploadBox.classList.remove('drag-over');
});

uploadBox.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadBox.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
});

uploadBox.addEventListener('click', () => {
  fileInput.click();
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFileSelect(fileInput.files[0]);
});

// ===========================
// FILE SELECT HANDLER
// ===========================
function handleFileSelect(file) {
  // Tekshirish — video fayl?
  if (!file.type.startsWith('video/')) {
    showError('Faqat video fayllar qabul qilinadi (MP4, MOV, AVI, MKV)');
    return;
  }

  // Tekshirish — hajm 500MB dan oshmasin
  const maxSize = 500 * 1024 * 1024; // 500MB
  if (file.size > maxSize) {
    showError('Fayl hajmi 500MB dan oshmasligi kerak');
    return;
  }

  selectedFile = file;

  // UI yangilash
  fileName.textContent = file.name;
  fileSize.textContent = formatFileSize(file.size);

  uploadBox.style.display = 'none';
  fileSelected.style.display = 'block';
  options.style.display = 'grid';
  submitBtn.style.display = 'flex';

  hideError();
}

// ===========================
// FILE REMOVE
// ===========================
fileRemove.addEventListener('click', () => {
  resetUpload();
});

function resetUpload() {
  selectedFile = null;
  fileInput.value = '';

  uploadBox.style.display = 'block';
  fileSelected.style.display = 'none';
  options.style.display = 'none';
  submitBtn.style.display = 'none';
  progressSection.style.display = 'none';
  resultSection.style.display = 'none';
  errorSection.style.display = 'none';

  resetProgress();
}

// ===========================
// SUBMIT — DUBBING BOSHLASH
// ===========================
submitBtn.addEventListener('click', async () => {
  if (!selectedFile) return;

  const sourceLang = document.getElementById('sourceLang').value;
  const targetLang = document.getElementById('targetLang').value;
  const lipSync    = document.getElementById('lipSync').value === 'true';

  // UI — progress ko'rsatish
  submitBtn.style.display = 'none';
  fileSelected.style.display = 'none';
  options.style.display = 'none';
  progressSection.style.display = 'block';

  setProgressStep('upload', 'active');
  updateProgress(5, 'Video yuklanmoqda...');

  try {
    // FormData yasash
    const formData = new FormData();
    formData.append('video', selectedFile);
    formData.append('source_lang', sourceLang);
    formData.append('target_lang', targetLang);
    formData.append('lip_sync', lipSync);

    // Backend ga yuborish
    const response = await fetch(`${API_URL}/dub`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Server xatosi');
    }

    const data = await response.json();
    jobId = data.job_id;

    setProgressStep('upload', 'done');
    updateProgress(15, 'Video yuklandi! Ovoz tanilmoqda...');

    // Polling — job holati tekshirish
    startPolling();

  } catch (err) {
    showError(err.message || 'Serverga ulanib bo\'lmadi. Keyinroq urinib ko\'ring.');
  }
});

// ===========================
// POLLING — JOB STATUS
// ===========================
function startPolling() {
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API_URL}/status/${jobId}`);
      if (!res.ok) throw new Error('Status so\'rovi xatosi');

      const data = await res.json();
      handleJobStatus(data);

    } catch (err) {
      clearInterval(pollInterval);
      showError('Server bilan aloqa uzildi. Sahifani yangilang.');
    }
  }, 3000); // har 3 soniyada tekshirish
}

// ===========================
// JOB STATUS HANDLER
// ===========================
function handleJobStatus(data) {
  const { status, progress, step, result_url, error } = data;

  switch (step) {
    case 'transcribing':
      setProgressStep('upload', 'done');
      setProgressStep('transcribe', 'active');
      updateProgress(progress || 25, 'Ovozlar tanilmoqda...');
      break;

    case 'translating':
      setProgressStep('transcribe', 'done');
      setProgressStep('translate', 'active');
      updateProgress(progress || 45, 'O\'zbekchaga tarjima qilinmoqda...');
      break;

    case 'tts':
      setProgressStep('translate', 'done');
      setProgressStep('tts', 'active');
      updateProgress(progress || 65, 'Ovoz yaratilmoqda...');
      break;

    case 'lipsync':
      setProgressStep('tts', 'done');
      setProgressStep('lipsync', 'active');
      updateProgress(progress || 82, 'Lip Sync qo\'shilmoqda...');
      break;

    case 'done':
      clearInterval(pollInterval);
      setProgressStep('lipsync', 'done');
      updateProgress(100, 'Tayyor!');

      setTimeout(() => {
        showResult(result_url);
      }, 800);
      break;

    case 'error':
      clearInterval(pollInterval);
      showError(error || 'Noma\'lum xatolik yuz berdi');
      break;
  }
}

// ===========================
// SHOW RESULT
// ===========================
function showResult(videoUrl) {
  progressSection.style.display = 'none';
  resultSection.style.display = 'block';

  const fullUrl = videoUrl.startsWith('http') ? videoUrl : `${API_URL}${videoUrl}`;
  resultVideo.src = fullUrl;
  downloadBtn.href = fullUrl;
}

// ===========================
// NEW VIDEO BUTTON
// ===========================
newVideoBtn.addEventListener('click', () => {
  resetUpload();
  jobId = null;
  if (pollInterval) clearInterval(pollInterval);
});

retryBtn.addEventListener('click', () => {
  resetUpload();
  jobId = null;
  if (pollInterval) clearInterval(pollInterval);
});

// ===========================
// PROGRESS HELPERS
// ===========================
const steps = ['upload', 'transcribe', 'translate', 'tts', 'lipsync'];

function setProgressStep(stepName, state) {
  const el = document.getElementById(`step-${stepName}`);
  if (!el) return;
  el.classList.remove('active', 'done');
  if (state) el.classList.add(state);

  // done bo'lganda emoji o'zgartirish
  if (state === 'done') {
    el.querySelector('.progress-step-icon').textContent = '✅';
  }
}

function updateProgress(percent, text) {
  progressBar.style.width = `${percent}%`;
  progressText.textContent = text;
}

function resetProgress() {
  progressBar.style.width = '0%';
  progressText.textContent = 'Tayyorlanmoqda...';

  steps.forEach(step => {
    const el = document.getElementById(`step-${step}`);
    if (!el) return;
    el.classList.remove('active', 'done');
  });

  // iconlarni qaytarish
  const icons = ['📤', '👂', '🌐', '🎙️', '🎬'];
  steps.forEach((step, i) => {
    const el = document.getElementById(`step-${step}`);
    if (el) el.querySelector('.progress-step-icon').textContent = icons[i];
  });
}

// ===========================
// ERROR HELPERS
// ===========================
function showError(message) {
  progressSection.style.display = 'none';
  submitBtn.style.display = selectedFile ? 'flex' : 'none';
  fileSelected.style.display = selectedFile ? 'block' : 'none';
  options.style.display = selectedFile ? 'grid' : 'none';

  errorSection.style.display = 'block';
  errorText.textContent = message;
}

function hideError() {
  errorSection.style.display = 'none';
}

// ===========================
// UTILS
// ===========================
function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ===========================
// SMOOTH SCROLL
// ===========================
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    e.preventDefault();
    const target = document.querySelector(anchor.getAttribute('href'));
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ===========================
// HEADER SCROLL EFFECT
// ===========================
window.addEventListener('scroll', () => {
  const header = document.querySelector('header');
  if (window.scrollY > 20) {
    header.style.borderBottomColor = 'rgba(42,42,58,0.8)';
  } else {
    header.style.borderBottomColor = 'var(--border)';
  }
});
