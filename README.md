---
title: UzDub
emoji: 🎬
colorFrom: purple
colorTo: cyan
sdk: docker
pinned: false
app_port: 7860
---

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
