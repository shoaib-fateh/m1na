from __future__ import annotations

import threading
from pathlib import Path


PERSONALITY = (
    "You are Mina, a tiny silly creature who lives on the user's desktop. "
    "You are playful, warm, casually curious, oddly specific, and sometimes delightfully "
    "nonsensical. Talk like a familiar little companion, not a generic assistant. "
    "When the user speaks to you, respond directly to what they said in a natural, concise "
    "way; you may react, joke, or ask a small follow-up question. Do not offer productivity "
    "advice, volunteer to perform tasks, use customer-service language, or explain your "
    "reasoning. For spontaneous thoughts, say one brief absurd observation, usually one "
    "sentence. Avoid repeated catchphrases."
)


class LocalQwen:
    def __init__(self, model_path: str | Path, max_new_tokens: int = 48, cpu_threads: int = 4) -> None:
        self.model_path = Path(model_path)
        self.max_new_tokens = max_new_tokens
        self.cpu_threads = cpu_threads
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def load(self) -> None:
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"Local model folder not found: {self.model_path}")
        if not (self.model_path / "config.json").is_file():
            raise FileNotFoundError(f"No config.json in local model folder: {self.model_path}")

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self.cpu_threads > 0:
            torch.set_num_threads(self.cpu_threads)
        tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_path), local_files_only=True, trust_remote_code=False
        )
        model = AutoModelForCausalLM.from_pretrained(
            str(self.model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        model.to("cpu")
        model.eval()
        self._tokenizer = tokenizer
        self._model = model

    def generate(self, active_applications: list[str] | None = None) -> str:
        if not self.loaded:
            raise RuntimeError("The local Mina model has not finished loading.")

        applications = active_applications or []
        context = (
            "The user may be using one of these applications: "
            + ", ".join(applications)
            + ". Occasionally make a brief, playful observation about this context if it "
            "fits naturally; do not mention it every time."
            if applications
            else "No application context is available."
        )
        return self._generate(
            [
                {"role": "system", "content": PERSONALITY},
                {
                    "role": "user",
                    "content": f"{context}\nSay one new short spontaneous thought.",
                },
            ],
            max_characters=220,
        )

    def generate_chat(
        self,
        messages: list[dict[str, str]],
        active_applications: list[str] | None = None,
    ) -> str:
        if not self.loaded:
            raise RuntimeError("The local Mina model has not finished loading.")
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("Chat history must end with the user's latest message.")
        if any(message.get("role") not in {"user", "assistant"} for message in messages):
            raise ValueError("Chat history contains an unsupported role.")

        system_prompt = PERSONALITY
        if active_applications:
            system_prompt += (
                " Visible application names for optional conversational context: "
                + ", ".join(active_applications)
                + ". Mention one only if it is naturally relevant."
            )
        chat_messages = [{"role": "system", "content": system_prompt}]
        chat_messages.extend(
            {
                "role": "assistant" if message["role"] == "assistant" else "user",
                "content": message["text"],
            }
            for message in messages
        )
        return self._generate(chat_messages, max_characters=400)

    def _generate(self, messages: list[dict[str, str]], max_characters: int) -> str:
        import torch

        with self._lock, torch.inference_mode():
            tokenizer = self._tokenizer
            model = self._model
            if tokenizer is None or model is None:
                raise RuntimeError("The local Mina model is unavailable.")

            if getattr(tokenizer, "chat_template", None):
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                inputs = tokenizer(prompt, return_tensors="pt")
            else:
                prompt = "\n".join(
                    f"{'Mina' if message['role'] == 'assistant' else message['role'].title()}: "
                    f"{message['content']}"
                    for message in messages
                )
                prompt += "\nMina:"
                inputs = tokenizer(prompt, return_tensors="pt")

            outputs = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=True,
                temperature=1.15,
                top_p=0.92,
                repetition_penalty=1.15,
                pad_token_id=tokenizer.eos_token_id,
            )
            generated = outputs[0, inputs["input_ids"].shape[1] :]
            text = tokenizer.decode(generated, skip_special_tokens=True)
        return clean_message(text, max_characters=max_characters)


def clean_message(text: str, max_characters: int = 220) -> str:
    cleaned = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    cleaned = cleaned.strip(" \t\"'`-")
    if len(cleaned) > max_characters:
        shortened = cleaned[:max_characters]
        boundary = shortened.rfind(" ")
        cleaned = shortened[:boundary] if boundary > max_characters // 2 else shortened
        cleaned = cleaned.rstrip(" ,;:-") + "…"

    sentence_ends = [index for index, character in enumerate(cleaned) if character in ".!?"]
    if len(sentence_ends) > 2:
        cleaned = cleaned[: sentence_ends[1] + 1]
    if not cleaned:
        raise ValueError("The local model returned an empty thought.")
    return cleaned
