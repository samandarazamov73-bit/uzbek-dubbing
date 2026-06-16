# 🎬 UzDub — AI Video Dubbing

Inglizcha videoni o'zbekchaga AI bilan dublyaj qiluvchi platforma.

## ✨ Imkoniyatlar

- 🎙️ Bir nechta ovozni alohida taniydi (erkak, ayol)
- 🌐 Intonatsiya va hissiyotlarni saqlagan holda tarjima qiladi
- 👄 Lip Sync — lab harakatlari bilan sinxronizatsiya
- 📱 Mobil qurilmalarda ham ishlaydi

## 🏗️ Arxitektura

```
Frontend (Netlify)  →  Backend (Hugging Face Spaces)
                              ↓
                    Whisper (ovoz tanish)
                              ↓
                    Helsinki-NLP (tarjima)
                              ↓
                    Fish Speech (TTS)
                              ↓
                    Wav2Lip (lip sync)
```

## 🚀 O'rnatish

### Frontend (Netlify)
1. GitHub reponi Netlify ga ulang
2. Build settings: `publish = frontend`
3. Deploy!

### Backend (Hugging Face Spaces)
1. huggingface.co da Space yarating
2. `backend/` papkasini yuklang
3. Secrets ga `HF_TOKEN` qo'shing

## 📁 Fayl tuzilmasi

```
uzbek-dubbing/
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── backend/
│   ├── main.py
│   ├── dubbing.py
│   └── requirements.txt
├── netlify.toml
└── README.md
```

## 🔧 Texnologiyalar

| Vosita | Maqsad |
|--------|--------|
| OpenAI Whisper | Ovoz → Matn |
| pyannote.audio | Kim gapirdi? |
| Helsinki-NLP | Tarjima |
| Fish Speech 1.5 | Matn → Ovoz |
| Wav2Lip | Lip Sync |
| FastAPI | Backend server |
| Netlify | Frontend hosting |

---
Made with ❤️ by Samandar
