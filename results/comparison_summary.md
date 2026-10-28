### Model comparison on the held-out test set

Test samples: 180 · 12 incident types · 4 severity levels · GPU: Tesla T4

| Approach | Type acc. | Type F1 | Sev. acc. | Sev. F1 | Parse fail | Infer ms | Train s | Peak train GB | Trainable params |
|---|---|---|---|---|---|---|---|---|---|
| Rules baseline | 0.872 | 0.875 | 0.683 | 0.741 | 0 | 0 | - | - | - |
| Qwen-0.5B zero-shot | 0.261 | 0.208 | 0.367 | 0.176 | 0 | 942 | - | - | - |
| Groq qwen3.8-27b zero-shot | 0.944 | 0.943 | 0.800 | 0.812 | 0 | 4168 | - | - | - |
| LoRA fp16 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 1209 | 511.6 | 6.857 | 8,798,208 |
| QLoRA 4-bit | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 1602 | 626.0 | 6.576 | 8,798,208 |

- Merged fp16 model reproduces QLoRA on 60 test logs: type acc 1.0, sev acc 0.9833.
- Cloud LLM baseline (Groq qwen/qwen3.8-27b) evaluated on all 180 test logs; its avg_inference_ms includes the 4.0 s throttle sleep used to stay inside the free-tier rate limit (about 170 ms is the API round trip).
