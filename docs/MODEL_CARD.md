---
license: apache-2.0
base_model: Qwen/Qwen2.5-0.5B-Instruct
base_model_relation: finetune
library_name: transformers
pipeline_tag: text-generation
language:
- en
tags:
- qwen2.5
- qlora
- lora
- peft
- incident-classification
- log-analysis
- sre
- devops
- synthetic-data
model-index:
- name: oncall-ai-incident-classifier
  results:
  - task:
      type: text-classification
      name: Production incident classification (type + severity)
    dataset:
      name: OnCall AI synthetic incident logs (test split, 180 logs)
      type: rachitst/oncall-ai
      split: test
    metrics:
    - type: accuracy
      name: Incident-type accuracy
      value: 1.0000
    - type: f1
      name: Incident-type macro-F1
      value: 1.0000
    - type: accuracy
      name: Severity accuracy
      value: 1.0000
    - type: f1
      name: Severity macro-F1
      value: 1.0000
---

# OnCall AI – Incident Classifier (Qwen2.5-0.5B-Instruct, QLoRA)

A small instruction-tuned model that reads a pasted production log excerpt and returns **one incident type out of 12**
and **one severity out of P1–P4** as a single JSON object. It is the classification stage of
[OnCall AI](https://github.com/rachitst/oncall-ai), an intelligent production-incident analyzer
(FastAPI + Gradio + LangGraph + FAISS runbook retrieval) built as an ESE mini project for *LLM Production & Deployment*.

- **Base model:** [Qwen/Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) (494 M parameters)
- **Method:** QLoRA (4-bit NF4 base, LoRA r=16, α=32) → adapter merged into fp16 base weights; this repo holds the **merged** model, no PEFT needed at inference
- **Task:** `log excerpt → {"incident_type": ..., "severity": ...}`
- **Live demo:** https://rachitst--oncall-ai-web.us-east.modal.run (the deployed app loads this exact checkpoint on CPU)
- **Code, dataset generator, training notebook, evaluation artefacts:** https://github.com/rachitst/oncall-ai
- **Author:** Rachit Manish Chheda

> **Important:** the training and test data are **synthetic** (template-generated logs). The perfect test score below
> says the model learned the generator's distribution, not that it is production-grade. See *Limitations*.

## Intended use

- First-pass triage of a pasted log excerpt (nginx, Kubernetes, PostgreSQL, systemd/journald, Python, Java style lines)
  into a fixed incident taxonomy plus a P1–P4 severity, on CPU, without calling a cloud LLM.
- Designed to be run **behind a verification step**: in OnCall AI the predicted type is used to retrieve runbook
  chunks, and the result is marked `needs_human` when retrieval finds nothing relevant.

Out of scope: open-ended log understanding, root-cause explanation, logs outside the 12 classes, non-English logs,
anything safety-critical without human review.

### Incident types (12)

| id | label |
|---|---|
| `database_connection_exhausted` | Database connection pool exhausted |
| `out_of_memory` | Out of memory (OOM) |
| `disk_space_full` | Disk space exhausted |
| `upstream_gateway_error` | Upstream / gateway failure (502/504) |
| `tls_certificate_expired` | TLS certificate expired / invalid |
| `kubernetes_crashloop` | Kubernetes CrashLoopBackOff |
| `application_exception` | Unhandled application exception |
| `dns_resolution_failure` | DNS resolution failure |
| `rate_limit_exceeded` | Rate limit / quota exceeded |
| `authentication_failure` | Authentication failure / credential issue |
| `high_latency_timeout` | High latency / request timeouts |
| `deployment_failure` | Deployment / rollout failure |

### Severity levels

| level | meaning |
|---|---|
| P1 | Critical - production outage or data at risk; page on-call immediately |
| P2 | Major - production degraded for many users; respond within 30 minutes |
| P3 | Minor - limited impact or non-production; handle in working hours |
| P4 | Low - informational, single occurrence, no user impact |

## Prompt format

The model was trained with the Qwen chat template and **exactly** this system prompt
(`app/prompts.py` in the repo; the app and the notebook share the file). Use it unchanged.

System:

```text
You are an SRE assistant. Classify the production log excerpt into exactly one incident_type from this list: database_connection_exhausted, out_of_memory, disk_space_full, upstream_gateway_error, tls_certificate_expired, kubernetes_crashloop, application_exception, dns_resolution_failure, rate_limit_exceeded, authentication_failure, high_latency_timeout, deployment_failure. Then assign a severity: P1 (production outage, all/most users, core flow down, data at risk), P2 (production degraded for many users, partial impact), P3 (limited impact, single host, non-production, self-recovered), P4 (informational, single occurrence in dev, within baseline). Answer with JSON only: {"incident_type": "...", "severity": "P1|P2|P3|P4"}
```

User:

```text
TASK: classify
LOG:
<the log excerpt>
```

Assistant (target):

```json
{"incident_type": "database_connection_exhausted", "severity": "P1"}
```

## How to use

```python
import json, math, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "rachitst/oncall-ai-incident-classifier"
tok = AutoTokenizer.from_pretrained(MODEL_ID)
device = "cuda" if torch.cuda.is_available() else "cpu"
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, torch_dtype=torch.float16 if device == "cuda" else torch.float32
).to(device).eval()

SYSTEM = ('You are an SRE assistant. Classify the production log excerpt into exactly one incident_type from this list: database_connection_exhausted, out_of_memory, disk_space_full, upstream_gateway_error, tls_certificate_expired, kubernetes_crashloop, application_exception, dns_resolution_failure, rate_limit_exceeded, authentication_failure, high_latency_timeout, deployment_failure. Then assign a severity: P1 (production outage, all/most users, core flow down, data at risk), P2 (production degraded for many users, partial impact), P3 (limited impact, single host, non-production, self-recovered), P4 (informational, single occurrence in dev, within baseline). Answer with JSON only: {"incident_type": "...", "severity": "P1|P2|P3|P4"}')

# a log from the held-out test split (label: database_connection_exhausted, P1)
log = """2026-09-05T20:55:02.000Z FATAL postgres[327]: FATAL:  sorry, too many clients already
2026-09-05T20:55:04.000Z DEBUG notification-svc cache hit ratio 93%
2026-09-05T20:55:05.000Z FATAL postgres[327]: FATAL:  remaining connection slots are reserved for non-replication superuser connections
2026-09-05T20:55:06.000Z ERROR notification-svc psycopg2.OperationalError: FATAL:  too many connections for role "app"
2026-09-05T20:55:14.000Z CRIT  monitor [prod] primary database unavailable; all write traffic failing on 3 nodes"""

messages = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"TASK: classify\nLOG:\n{log}"}]
prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=2048).to(device)

with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=48, do_sample=False,
                         output_scores=True, return_dict_in_generate=True,
                         pad_token_id=tok.pad_token_id or tok.eos_token_id)

new = out.sequences[0][inputs["input_ids"].shape[1]:]
text = tok.decode(new, skip_special_tokens=True)
label = json.loads(text)                       # {"incident_type": "...", "severity": "P1"}

# confidence = geometric mean of the generated tokens' probabilities (what the app reports)
logps = []
for step, t in zip(out.scores, new):
    logps.append(torch.log_softmax(step[0].float(), dim=-1)[t].item())
    if t.item() == tok.eos_token_id:
        break
confidence = math.exp(sum(logps) / len(logps))
print(label, round(confidence, 3))
# -> {'incident_type': 'database_connection_exhausted', 'severity': 'P1'} 1.0   (measured on CPU, fp32)
```

Greedy decoding, `max_new_tokens=48`. The reply is a single JSON object; the app parses it with a tolerant
regex and treats a parse failure as low confidence. Parse failures on the test set: 0.

## Training data

Generated by `data/generate_dataset.py` (seed 42) in the repo. Each sample is a short multi-line log excerpt
built from hand-written templates that imitate real nginx, Kubernetes, PostgreSQL, systemd/journald, Python and
Java log lines, with randomised hosts, IPs, timestamps, services and numbers plus interleaved unrelated INFO lines
as noise. Severity is derived from the blast radius stated **in the log text** (environment, error rate, number of
affected hosts/pods, user impact), so the model has to read the context rather than spot a keyword.

| | |
|---|---|
| Samples | 1200 (840 train / 180 val / 180 test, stratified) |
| Incident types | 12, balanced (100 each) |
| Severity distribution | P1 168, P2 420, P3 396, P4 216 |
| Environment distribution | prod 672, staging 312, dev 216 |
| Average length | 4.21 lines, 455 characters |

Only the assistant turn (the JSON label) contributes to the loss; prompt tokens are masked with `-100`.
Sequences are truncated at 512 tokens.

## Training procedure

Notebook: [`training/OnCall_AI_Training.ipynb`](https://github.com/rachitst/oncall-ai/blob/main/training/OnCall_AI_Training.ipynb),
run on Google Colab (Tesla T4, 2026-10-28). Two adapters were trained with identical hyper-parameters; the
**QLoRA** one is what this repo ships.

| hyper-parameter | value |
|---|---|
| Base | `Qwen/Qwen2.5-0.5B-Instruct` |
| Quantisation (QLoRA run) | 4-bit NF4, double quantisation, fp16 compute (bitsandbytes) |
| LoRA | r=16, α=32, dropout 0.05 |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Trainable parameters | 8,798,208 of 323,917,696 (2.716 %) |
| Epochs | 3 |
| Learning rate | 0.0002, cosine schedule, 16 warm-up steps |
| Batch | 4 per device × 2 gradient accumulation (effective 8) |
| Optimizer | paged AdamW 8-bit (QLoRA) / AdamW (LoRA fp16) |
| Precision | fp16 mixed |
| Max sequence length | 512 |
| Seed | 42 |
| Software | transformers 5.x `Trainer`, peft, bitsandbytes |

| run | train time | peak GPU memory | final eval loss |
|---|---|---|---|
| QLoRA 4-bit (this model) | 626 s | 6.58 GB | 0.0001 |
| LoRA fp16 (comparison) | 512 s | 6.86 GB | 0.0001 |

![Loss curves](figures/06_loss_curves.png)

**Merge:** the QLoRA adapter was merged into an fp16 copy of the base weights with
`PeftModel.merge_and_unload()` and saved with safetensors (988 MB). A sanity check of the merged model on the first
60 test logs reproduced the adapter: type accuracy 1.000, severity accuracy 0.983.

## Evaluation

Held-out test split: 180 logs, 12 types, 4 severities. Metrics: accuracy and macro-F1 for each of the two
labels, number of unparseable replies, and mean inference time per log on a Tesla T4.

| approach | type acc | type F1 | sev acc | sev F1 | parse fail | ms/log (T4) | train s | peak GB |
|---|---|---|---|---|---|---|---|---|
| Rules baseline (keyword scoring) | 0.872 | 0.875 | 0.683 | 0.741 | 0 | 0 | - | - |
| Qwen2.5-0.5B-Instruct zero-shot | 0.261 | 0.208 | 0.367 | 0.176 | 0 | 942 | - | - |
| Groq qwen/qwen3.8-27b zero-shot | 0.944 | 0.943 | 0.800 | 0.812 | 0 | 4168 | - | - |
| LoRA fp16 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 1209 | 512 | 6.86 |
| **QLoRA 4-bit (this model)** | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 1602 | 626 | 6.58 |

Notes:
- The Groq row's latency includes a 4.0 s throttle sleep used to stay inside the free-tier rate limit; the API
  round trip itself is about 170 ms.
- The QLoRA latency is for the 4-bit adapter model on the T4; the merged fp16 checkpoint in this repo ran at
  611 ms/log on the same GPU in the sanity check.

![Type accuracy and F1](figures/01_type_accuracy_f1.png)
![Severity accuracy and F1](figures/02_severity_accuracy_f1.png)
![Confusion matrix](figures/05_confusion_matrix.png)

### Inference latency on CPU (merged model, fp32, greedy, in the deployed app)

| machine | classifier latency per log |
|---|---|
| Modal container, 2 vCPU / 4 GB | 3.6 – 5.0 s (7 hand-written logs) |
| Laptop, Celeron N4500, 2 cores, no AVX | 12.9 – 17.0 s |
| Tesla T4 (fp16) | 0.6 s |

Cold start on Modal (download from this repo + load) was about 37 s; loading from a warm cache takes ~5 s.

## Limitations

- **Synthetic data.** Train, validation and test logs all come from the same template generator. 1.000 on the test
  split means the generator's patterns were learned, not that real production logs will be classified this well.
- **Observed distribution-shift miss.** On a hand-written log (expired TLS certificate in prod, "100 % of requests
  failing") the model answers severity **P2 with confidence 0.999** where P1 is expected, because the generator never
  phrases a P1 that way. High confidence is therefore not a reliability signal outside the training distribution.
- **Closed taxonomy.** Every input gets one of the 12 classes; unrelated or noisy text is still assigned a class
  (a nonsense log was classified `deployment_failure` at 0.977). Use retrieval or a rules check to catch this,
  as the OnCall AI workflow does.
- **English, short excerpts only.** Inputs are truncated at 2048 tokens; the app further caps logs at 20,000 characters.
- **Not a safety or security tool.** No PII redaction is built in (the app redacts before calling the model).

## Files

| file | content |
|---|---|
| `model.safetensors` | merged fp16 weights, 988 MB |
| `config.json`, `generation_config.json` | Qwen2 architecture config |
| `tokenizer.json`, `tokenizer_config.json`, `chat_template.jinja` | unchanged Qwen2.5 tokenizer and chat template |
| `figures/` | evaluation charts rendered from `results/comparison.json` in the repo |

## License

The base model, Qwen2.5-0.5B-Instruct, is released under Apache-2.0; this fine-tune is released under the same license.

## Citation

```bibtex
@misc{chheda2026oncallai,
  title  = {OnCall AI: Intelligent Production Incident Analyzer -- QLoRA incident classifier},
  author = {Chheda, Rachit Manish},
  year   = {2026},
  url    = {https://github.com/rachitst/oncall-ai}
}
```
