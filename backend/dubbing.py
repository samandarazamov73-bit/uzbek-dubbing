import os
import asyncio
import subprocess
import tempfile
import json
from pathlib import Path

# ===========================
# DUBBING PIPELINE
# ===========================
class DubbingPipeline:
    """
    To'liq dublyaj pipeline:
    1. Whisper  → ovozni matnга aylantiradi (kim gapirdi, qachon)
    2. Helsinki NLP / argostranslate → matnni o'zbekchaga tarjima qiladi
    3. Fish Speech (TTS) → erkak/ayol ovozi bilan o'zbekcha nutq yaratadi
    4. FFmpeg  → ovozni videoga qo'shadi
    5. Wav2Lip → lip sync (ixtiyoriy)
    """

    def __init__(self, job_id: str, jobs: dict):
        self.job_id = job_id
        self.jobs = jobs

    def _update(self, step: str, progress: int, message: str = ""):
        """Job holatini yangilash"""
        self.jobs[self.job_id].update({
            "step": step,
            "progress": progress,
        })
        print(f"[{self.job_id[:8]}] {step} — {progress}% {message}")

    # ===========================
    # MAIN RUN
    # ===========================
    async def run(
        self,
        input_path: str,
        output_path: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        lip_sync: bool = True,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 1. Audio ajratib olish
            self._update("transcribing", 15, "Audiо ajratilmoqda...")
            audio_path = tmpdir / "audio.wav"
            await self._extract_audio(input_path, str(audio_path))

            # 2. Whisper — transkripsiya + speaker diarization
            self._update("transcribing", 30, "Ovozlar tanilmoqda...")
            segments = await self._transcribe(str(audio_path), source_lang)

            # 3. Tarjima
            self._update("translating", 45, "O'zbekchaga tarjima qilinmoqda...")
            translated_segments = await self._translate_segments(segments, source_lang, target_lang)

            # 4. TTS — har bir speaker uchun alohida ovoz
            self._update("tts", 65, "Ovozlar yaratilmoqda...")
            dubbed_audio = await self._generate_tts(
                translated_segments,
                str(audio_path),
                tmpdir
            )

            # 5. Videoga ovoz qo'shish
            self._update("lipsync", 80, "Video yig'ilmoqda...")
            if lip_sync:
                await self._add_lipsync(input_path, dubbed_audio, output_path, tmpdir)
            else:
                await self._merge_audio_video(input_path, dubbed_audio, output_path)

            self._update("done", 100, "Tayyor!")

    # ===========================
    # 1. AUDIO EXTRACTION
    # ===========================
    async def _extract_audio(self, video_path: str, audio_path: str):
        """FFmpeg bilan videoden audio ajratib olish"""
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",                    # video yo'q
            "-acodec", "pcm_s16le",   # WAV format
            "-ar", "16000",           # 16kHz — Whisper uchun ideal
            "-ac", "1",               # mono
            "-y",                     # overwrite
            audio_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg audio ajratishda xato: {stderr.decode()}")

    # ===========================
    # 2. TRANSCRIPTION + DIARIZATION
    # ===========================
    async def _transcribe(self, audio_path: str, source_lang: str) -> list:
        """
        Whisper bilan matnni aniqlash + pyannote bilan kim gapirganini bilish
        Returns: [{"speaker": "SPEAKER_0", "start": 0.0, "end": 2.5, "text": "Hello", "gender": "male"}, ...]
        """
        loop = asyncio.get_event_loop()
        segments = await loop.run_in_executor(None, self._transcribe_sync, audio_path, source_lang)
        return segments

    def _transcribe_sync(self, audio_path: str, source_lang: str) -> list:
        import whisper
        import torch

        # Model yuklash (birinchi marta slow, keyingi marta tez)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("base", device=device)

        print(f"  Whisper model: base, device: {device}")

        result = model.transcribe(
            audio_path,
            language=source_lang,
            word_timestamps=True,
            verbose=False
        )

        segments = []
        for seg in result["segments"]:
            segments.append({
                "speaker": "SPEAKER_0",  # default — diarization qo'shiladi
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "gender": "male",  # default
            })

        # Speaker diarization (pyannote mavjud bo'lsa)
        try:
            segments = self._add_diarization(audio_path, segments)
        except Exception as e:
            print(f"  Diarization o'tkazib yuborildi: {e}")

        return segments

    def _add_diarization(self, audio_path: str, segments: list) -> list:
        """
        Pyannote bilan kim gapirganini aniqlash
        Har bir segmentga speaker va gender belgilash
        """
        from pyannote.audio import Pipeline
        import torch

        # HuggingFace token kerak (bepul)
        hf_token = os.environ.get("HF_TOKEN", "")
        if not hf_token:
            print("  HF_TOKEN yo'q — diarization o'tkazildi")
            return segments

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        diarization = pipeline(audio_path)

        # Har bir segmentni speaker bilan moslashtirish
        speaker_map = {}
        speaker_count = 0

        for seg in segments:
            mid = (seg["start"] + seg["end"]) / 2
            best_speaker = None
            best_overlap = 0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap = min(turn.end, seg["end"]) - max(turn.start, seg["start"])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker

            if best_speaker:
                if best_speaker not in speaker_map:
                    speaker_map[best_speaker] = f"SPEAKER_{speaker_count}"
                    speaker_count += 1
                seg["speaker"] = speaker_map[best_speaker]

        # Gender aniqlash (ovoz balandligi bo'yicha taxmin)
        self._detect_gender(audio_path, segments)

        return segments

    def _detect_gender(self, audio_path: str, segments: list):
        """
        Har bir speaker uchun gender aniqlash
        Oddiy usul: ovoz chastotasi bo'yicha
        """
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(audio_path, sr=None)
            speaker_pitches = {}

            for seg in segments:
                start_sample = int(seg["start"] * sr)
                end_sample = int(seg["end"] * sr)
                chunk = y[start_sample:end_sample]

                if len(chunk) < sr * 0.1:
                    continue

                # F0 (fundamental frequency) hisoblash
                pitches, magnitudes = librosa.piptrack(y=chunk, sr=sr)
                pitch_values = pitches[magnitudes > magnitudes.mean()]

                if len(pitch_values) > 0:
                    mean_pitch = np.mean(pitch_values[pitch_values > 0])
                    speaker = seg["speaker"]
                    if speaker not in speaker_pitches:
                        speaker_pitches[speaker] = []
                    speaker_pitches[speaker].append(mean_pitch)

            # Gender belgilash: <165Hz erkak, ≥165Hz ayol
            speaker_gender = {}
            for speaker, pitches in speaker_pitches.items():
                avg_pitch = sum(pitches) / len(pitches)
                speaker_gender[speaker] = "female" if avg_pitch >= 165 else "male"

            for seg in segments:
                if seg["speaker"] in speaker_gender:
                    seg["gender"] = speaker_gender[seg["speaker"]]

        except Exception as e:
            print(f"  Gender aniqlashda xato: {e}")

    # ===========================
    # 3. TRANSLATION
    # ===========================
    async def _translate_segments(self, segments: list, source_lang: str, target_lang: str) -> list:
        """Matnni o'zbekchaga tarjima qilish"""
        loop = asyncio.get_event_loop()
        translated = await loop.run_in_executor(
            None, self._translate_sync, segments, source_lang, target_lang
        )
        return translated

    def _translate_sync(self, segments: list, source_lang: str, target_lang: str) -> list:
        """
        Helsinki-NLP modeli bilan tarjima
        En → Uz uchun: Helsinki-NLP/opus-mt-en-uz
        """
        from transformers import MarianMTModel, MarianTokenizer

        model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
        print(f"  Tarjima modeli: {model_name}")

        try:
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
        except Exception:
            # Fallback: en → uz to'g'ridan-to'g'ri model bo'lmasa
            # en → ru → uz yo'li
            print("  To'g'ridan-to'g'ri model topilmadi, fallback ishlatilmoqda...")
            return self._translate_via_english(segments, source_lang, target_lang)

        translated = []
        texts = [seg["text"] for seg in segments]

        # Batch tarjima
        batch_size = 8
        all_translated = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=512)
            outputs = model.generate(**inputs, num_beams=4, max_length=512)
            decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
            all_translated.extend(decoded)

        for i, seg in enumerate(segments):
            translated_seg = seg.copy()
            translated_seg["translated_text"] = all_translated[i] if i < len(all_translated) else seg["text"]
            translated.append(translated_seg)

        return translated

    def _translate_via_english(self, segments: list, source_lang: str, target_lang: str) -> list:
        """
        Fallback: argostranslate ishlatish
        """
        try:
            import argostranslate.package
            import argostranslate.translate

            # Paketlarni yuklash
            argostranslate.package.update_package_index()
            available_packages = argostranslate.package.get_available_packages()

            package = next(
                filter(lambda x: x.from_code == source_lang and x.to_code == target_lang, available_packages),
                None
            )

            if package:
                argostranslate.package.install_from_path(package.download())

            translated = []
            for seg in segments:
                try:
                    tr_text = argostranslate.translate.translate(seg["text"], source_lang, target_lang)
                except Exception:
                    tr_text = seg["text"]

                translated_seg = seg.copy()
                translated_seg["translated_text"] = tr_text
                translated.append(translated_seg)

            return translated

        except Exception as e:
            print(f"  Argostranslate xatosi: {e}")
            # So'nggi fallback: tarjima qilmasdan qaytarish
            result = []
            for seg in segments:
                s = seg.copy()
                s["translated_text"] = seg["text"]
                result.append(s)
            return result

    # ===========================
    # 4. TEXT-TO-SPEECH
    # ===========================
    async def _generate_tts(self, segments: list, original_audio: str, tmpdir: Path) -> str:
        """
        Fish Speech bilan har bir speaker uchun TTS
        Erkak va ayol ovozlari alohida
        """
        loop = asyncio.get_event_loop()
        dubbed_path = await loop.run_in_executor(
            None, self._tts_sync, segments, original_audio, tmpdir
        )
        return dubbed_path

    def _tts_sync(self, segments: list, original_audio: str, tmpdir: Path) -> str:
        """
        TTS generatsiya + vaqt moslashtirish
        """
        import torch
        import numpy as np
        import soundfile as sf

        # Original audio uzunligini olish
        import librosa
        original_y, original_sr = librosa.load(original_audio, sr=22050)
        total_duration = len(original_y) / original_sr

        # Bo'sh audio buffer (original bilan bir xil uzunlik)
        output_sr = 22050
        output_audio = np.zeros(int(total_duration * output_sr))

        # TTS modeli yuklash
        tts_model = self._load_tts_model()

        for i, seg in enumerate(segments):
            text = seg.get("translated_text", seg["text"])
            if not text.strip():
                continue

            start_sample = int(seg["start"] * output_sr)
            end_sample = int(seg["end"] * output_sr)
            target_duration = seg["end"] - seg["start"]

            try:
                # TTS generatsiya
                gender = seg.get("gender", "male")
                audio_chunk = tts_model.generate(
                    text=text,
                    gender=gender,
                    language="uz",
                )

                # Vaqt moslashtirish (stretch/squeeze)
                if len(audio_chunk) > 0:
                    chunk_duration = len(audio_chunk) / output_sr
                    if abs(chunk_duration - target_duration) > 0.1:
                        # Librosa bilan vaqt o'zgartirish
                        rate = chunk_duration / target_duration
                        rate = max(0.5, min(2.0, rate))  # 0.5x - 2x orasida
                        audio_chunk = librosa.effects.time_stretch(audio_chunk.astype(np.float32), rate=rate)

                    # Output bufferga yozish
                    end_pos = min(start_sample + len(audio_chunk), len(output_audio))
                    audio_chunk_trimmed = audio_chunk[:end_pos - start_sample]
                    output_audio[start_sample:end_pos] = audio_chunk_trimmed

            except Exception as e:
                print(f"  Segment {i} TTS xatosi: {e}")
                continue

        # Saqlash
        output_path = str(tmpdir / "dubbed_audio.wav")
        sf.write(output_path, output_audio, output_sr)

        return output_path

    def _load_tts_model(self):
        """TTS model wrapper"""
        return TTSModelWrapper()

    # ===========================
    # 5. LIP SYNC
    # ===========================
    async def _add_lipsync(self, video_path: str, audio_path: str, output_path: str, tmpdir: Path):
        """Wav2Lip bilan lip sync"""
        try:
            wav2lip_path = Path(os.environ.get("WAV2LIP_PATH", "./Wav2Lip"))

            if not wav2lip_path.exists():
                print("  Wav2Lip topilmadi — oddiy merge ishlatilmoqda")
                await self._merge_audio_video(video_path, audio_path, output_path)
                return

            checkpoint = wav2lip_path / "checkpoints" / "wav2lip_gan.pth"

            cmd = [
                "python", str(wav2lip_path / "inference.py"),
                "--checkpoint_path", str(checkpoint),
                "--face", video_path,
                "--audio", audio_path,
                "--outfile", output_path,
                "--resize_factor", "1",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(wav2lip_path)
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                print(f"  Wav2Lip xatosi — oddiy merge ishlatilmoqda: {stderr.decode()[:200]}")
                await self._merge_audio_video(video_path, audio_path, output_path)

        except Exception as e:
            print(f"  Lip sync xatosi: {e} — oddiy merge ishlatilmoqda")
            await self._merge_audio_video(video_path, audio_path, output_path)

    async def _merge_audio_video(self, video_path: str, audio_path: str, output_path: str):
        """FFmpeg bilan video + audio birlashtirish"""
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",           # video o'zgartirilmaydi
            "-c:a", "aac",            # audio AAC formatga
            "-map", "0:v:0",          # original videodan
            "-map", "1:a:0",          # yangi audiodan
            "-shortest",              # qisqaroq bo'yicha kesish
            "-y",
            output_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg merge xatosi: {stderr.decode()}")


# ===========================
# TTS MODEL WRAPPER
# ===========================
class TTSModelWrapper:
    """
    Fish Speech yoki CoquiTTS wrapper
    Uzbek tilida erkak/ayol ovozi
    """

    def __init__(self):
        self.model = None
        self.model_type = None
        self._load()

    def _load(self):
        """Mavjud TTS modelni yuklash"""

        # 1. Fish Speech sinab ko'rish
        try:
            self._load_fish_speech()
            self.model_type = "fish_speech"
            print("  ✅ Fish Speech modeli yuklandi")
            return
        except Exception as e:
            print(f"  Fish Speech yuklanmadi: {e}")

        # 2. Coqui TTS sinab ko'rish
        try:
            self._load_coqui()
            self.model_type = "coqui"
            print("  ✅ Coqui TTS modeli yuklandi")
            return
        except Exception as e:
            print(f"  Coqui TTS yuklanmadi: {e}")

        # 3. gTTS fallback (internet kerak)
        self.model_type = "gtts"
        print("  ⚠️ gTTS (fallback) ishlatilmoqda")

    def _load_fish_speech(self):
        """Fish Speech 1.5 — eng yaxshi ovoz sifati"""
        import sys
        fish_path = os.environ.get("FISH_SPEECH_PATH", "./fish-speech")
        if fish_path not in sys.path:
            sys.path.insert(0, fish_path)
        from tools.api import TTSClient
        self.model = TTSClient()

    def _load_coqui(self):
        """Coqui XTTS-v2"""
        from TTS.api import TTS
        self.model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

    def generate(self, text: str, gender: str = "male", language: str = "uz") -> "np.ndarray":
        """Matndan ovoz yaratish"""
        import numpy as np
        import io
        import soundfile as sf

        if self.model_type == "fish_speech":
            return self._generate_fish(text, gender, language)
        elif self.model_type == "coqui":
            return self._generate_coqui(text, gender, language)
        else:
            return self._generate_gtts(text, language)

    def _generate_fish(self, text: str, gender: str, language: str):
        """Fish Speech bilan generatsiya"""
        import numpy as np
        # Reference ovoz tanlash (erkak yoki ayol)
        ref_voice = f"voices/{gender}_uz.wav"
        audio = self.model.tts(text=text, reference=ref_voice, language=language)
        return np.array(audio)

    def _generate_coqui(self, text: str, gender: str, language: str):
        """Coqui XTTS-v2 bilan generatsiya"""
        import numpy as np
        import io
        import soundfile as sf

        speaker_wav = f"voices/{gender}_uz.wav"
        if not os.path.exists(speaker_wav):
            speaker_wav = None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        self.model.tts_to_file(
            text=text,
            language=language,
            speaker_wav=speaker_wav,
            file_path=tmp_path
        )
        audio, _ = sf.read(tmp_path)
        os.unlink(tmp_path)
        return audio

    def _generate_gtts(self, text: str, language: str):
        """gTTS fallback (internet kerak, ovoz sifati past)"""
        import numpy as np
        import io
        import soundfile as sf
        from gtts import gTTS
        import tempfile

        tts = gTTS(text=text, lang=language if language in ["uz", "en", "ru"] else "en")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            tts.save(tmp_path)

        # MP3 → numpy
        proc = subprocess.run(
            ["ffmpeg", "-i", tmp_path, "-f", "f32le", "-ar", "22050", "-ac", "1", "-"],
            capture_output=True
        )
        os.unlink(tmp_path)

        if proc.returncode == 0:
            return np.frombuffer(proc.stdout, dtype=np.float32)
        return np.zeros(22050)  # 1 soniya bo'sh ovoz
