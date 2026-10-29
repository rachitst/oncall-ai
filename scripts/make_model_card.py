"""Build the Hugging Face model card from measured artefacts (results/comparison.json, smoke tests, dataset stats)."""
import json, os, sys
ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
from app.prompts import CLASSIFY_SYSTEM  # exact prompt used for training and inference
from data.taxonomy import INCIDENT_TYPES, SEVERITIES  # noqa

cmp = json.load(open(f"{ROOT}/results/comparison.json"))
cfg = cmp["config"]
runs = {r["name"]: r for r in cmp["runs"]}
stats = json.load(open(f"{ROOT}/data/dataset/dataset_stats.json"))
modal = json.load(open(f"{ROOT}/results/smoke_test_modal.json"))
local = json.load(open(f"{ROOT}/results/smoke_test_local.json"))
def cls_ms(d): return [r["result"]["classification"]["latency_ms"] for r in d["records"]]
m_ms, l_ms = cls_ms(modal), cls_ms(local)
q = runs["QLoRA 4-bit"]; lo = runs["LoRA fp16"]
total_params = 323_917_696  # printed by the notebook: trainable 8,798,208 / 323,917,696 (2.716%)
pct = 100 * q["trainable_params"] / total_params

def row(name, r, train=True):
    t = f'{r["train_time_s"]:.0f}' if train and r.get("train_time_s") else "-"
    mem = f'{r["peak_train_memory_gb"]:.2f}' if train and r.get("peak_train_memory_gb") else "-"
    return (f'| {name} | {r["type_accuracy"]:.3f} | {r["type_macro_f1"]:.3f} | {r["severity_accuracy"]:.3f} | '
            f'{r["severity_macro_f1"]:.3f} | {r["parse_failures"]} | {r["avg_inference_ms"]:.0f} | {t} | {mem} |')

type_rows = "\n".join(f"| `{k}` | {v['label'] if isinstance(v, dict) else v} |" for k, v in INCIDENT_TYPES.items())
sev_rows = "\n".join(f"| {k} | {v} |" for k, v in SEVERITIES.items())
sev_dist = ", ".join(f"{k} {stats['severity'][k]}" for k in ["P1", "P2", "P3", "P4"])
env_dist = ", ".join(f"{k} {v}" for k, v in stats["environment"].items())

card = f"""---
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
      value: {q["type_accuracy"]:.4f}
    - type: f1
      name: Incident-type macro-F1
      value: {q["type_macro_f1"]:.4f}
    - type: accuracy
      name: Severity accuracy
      value: {q["severity_accuracy"]:.4f}
    - type: f1
      name: Severity macro-F1
      value: {q["severity_macro_f1"]:.4f}
---

# OnCall AI – Incident Classifier (Qwen2.5-0.5B-Instruct, QLoRA)

A small instruction-tuned model that reads a pasted production log excerpt and returns **one incident type out of 12**
and **one severity out of P1–P4** as a single JSON object. It is the classification stage of
[OnCall AI](https://github.com/rachitst/oncall-ai), an intelligent production-incident analyzer
(FastAPI + Gradio + LangGraph + FAISS runbook retrieval) built as an ESE mini project for *LLM Production & Deployment*.

- **Base model:** [Qwen/Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) (494 M parameters)
- **Method:** QLoRA (4-bit NF4 base, LoRA r={cfg["lora_r"]}, α={cfg["lora_alpha"]}) → adapter merged into fp16 base weights; this repo holds the **merged** model, no PEFT needed at inference
- **Task:** `log excerpt → {{"incident_type": ..., "severity": ...}}`
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
{type_rows}

### Severity levels

| level | meaning |
|---|---|
{sev_rows}

## Prompt format

The model was trained with the Qwen chat template and **exactly** this system prompt
(`app/prompts.py` in the repo; the app and the notebook share the file). Use it unchanged.

System:

```text
{CLASSIFY_SYSTEM}
```

User:

```text
TASK: classify
LOG:
<the log excerpt>
```

Assistant (target):

```json
{{"incident_type": "database_connection_exhausted", "severity": "P1"}}
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

SYSTEM = ({CLASSIFY_SYSTEM!r})

# a log from the held-out test split (label: database_connection_exhausted, P1)
log = \"\"\"2026-09-05T20:55:02.000Z FATAL postgres[327]: FATAL:  sorry, too many clients already
2026-09-05T20:55:04.000Z DEBUG notification-svc cache hit ratio 93%
2026-09-05T20:55:05.000Z FATAL postgres[327]: FATAL:  remaining connection slots are reserved for non-replication superuser connections
2026-09-05T20:55:06.000Z ERROR notification-svc psycopg2.OperationalError: FATAL:  too many connections for role "app"
2026-09-05T20:55:14.000Z CRIT  monitor [prod] primary database unavailable; all write traffic failing on 3 nodes\"\"\"

messages = [{{"role": "system", "content": SYSTEM}},
            {{"role": "user", "content": f"TASK: classify\\nLOG:\\n{{log}}"}}]
prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=2048).to(device)

with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=48, do_sample=False,
                         output_scores=True, return_dict_in_generate=True,
                         pad_token_id=tok.pad_token_id or tok.eos_token_id)

new = out.sequences[0][inputs["input_ids"].shape[1]:]
text = tok.decode(new, skip_special_tokens=True)
label = json.loads(text)                       # {{"incident_type": "...", "severity": "P1"}}

# confidence = geometric mean of the generated tokens' probabilities (what the app reports)
logps = []
for step, t in zip(out.scores, new):
    logps.append(torch.log_softmax(step[0].float(), dim=-1)[t].item())
    if t.item() == tok.eos_token_id:
        break
confidence = math.exp(sum(logps) / len(logps))
print(label, round(confidence, 3))
# -> {{'incident_type': 'database_connection_exhausted', 'severity': 'P1'}} 1.0   (measured on CPU, fp32)
```

Greedy decoding, `max_new_tokens=48`. The reply is a single JSON object; the app parses it with a tolerant
regex and treats a parse failure as low confidence. Parse failures on the test set: {q["parse_failures"]}.

## Training data

Generated by `data/generate_dataset.py` (seed {stats["seed"]}) in the repo. Each sample is a short multi-line log excerpt
built from hand-written templates that imitate real nginx, Kubernetes, PostgreSQL, systemd/journald, Python and
Java log lines, with randomised hosts, IPs, timestamps, services and numbers plus interleaved unrelated INFO lines
as noise. Severity is derived from the blast radius stated **in the log text** (environment, error rate, number of
affected hosts/pods, user impact), so the model has to read the context rather than spot a keyword.

| | |
|---|---|
| Samples | {stats["total"]} ({stats["train"]} train / {stats["val"]} val / {stats["test"]} test, stratified) |
| Incident types | 12, balanced (100 each) |
| Severity distribution | {sev_dist} |
| Environment distribution | {env_dist} |
| Average length | {stats["avg_lines"]} lines, {stats["avg_chars"]:.0f} characters |

Only the assistant turn (the JSON label) contributes to the loss; prompt tokens are masked with `-100`.
Sequences are truncated at {cfg["max_len"]} tokens.

## Training procedure

Notebook: [`training/OnCall_AI_Training.ipynb`](https://github.com/rachitst/oncall-ai/blob/main/training/OnCall_AI_Training.ipynb),
run on Google Colab (Tesla T4, 2026-10-28). Two adapters were trained with identical hyper-parameters; the
**QLoRA** one is what this repo ships.

| hyper-parameter | value |
|---|---|
| Base | `{cfg["base_model"]}` |
| Quantisation (QLoRA run) | 4-bit NF4, double quantisation, fp16 compute (bitsandbytes) |
| LoRA | r={cfg["lora_r"]}, α={cfg["lora_alpha"]}, dropout 0.05 |
| Target modules | {", ".join(f"`{m}`" for m in cfg["target_modules"])} |
| Trainable parameters | {q["trainable_params"]:,} of {total_params:,} ({pct:.3f} %) |
| Epochs | {cfg["epochs"]} |
| Learning rate | {cfg["lr"]}, cosine schedule, 16 warm-up steps |
| Batch | 4 per device × 2 gradient accumulation (effective 8) |
| Optimizer | paged AdamW 8-bit (QLoRA) / AdamW (LoRA fp16) |
| Precision | fp16 mixed |
| Max sequence length | {cfg["max_len"]} |
| Seed | {stats["seed"]} |
| Software | transformers 5.x `Trainer`, peft, bitsandbytes |

| run | train time | peak GPU memory | final eval loss |
|---|---|---|---|
| QLoRA 4-bit (this model) | {q["train_time_s"]:.0f} s | {q["peak_train_memory_gb"]:.2f} GB | {q["final_eval_loss"]} |
| LoRA fp16 (comparison) | {lo["train_time_s"]:.0f} s | {lo["peak_train_memory_gb"]:.2f} GB | {lo["final_eval_loss"]} |

![Loss curves](figures/06_loss_curves.png)

**Merge:** the QLoRA adapter was merged into an fp16 copy of the base weights with
`PeftModel.merge_and_unload()` and saved with safetensors (988 MB). A sanity check of the merged model on the first
60 test logs reproduced the adapter: type accuracy 1.000, severity accuracy 0.983.

## Evaluation

Held-out test split: {cmp["n_test"]} logs, 12 types, 4 severities. Metrics: accuracy and macro-F1 for each of the two
labels, number of unparseable replies, and mean inference time per log on a {cmp["gpu"]}.

| approach | type acc | type F1 | sev acc | sev F1 | parse fail | ms/log (T4) | train s | peak GB |
|---|---|---|---|---|---|---|---|---|
{row("Rules baseline (keyword scoring)", runs["Rules baseline"], False)}
{row("Qwen2.5-0.5B-Instruct zero-shot", runs["Qwen-0.5B zero-shot"], False)}
{row("Groq qwen/qwen3.8-27b zero-shot", runs["Groq qwen3.8-27b zero-shot"], False)}
{row("LoRA fp16", lo)}
{row("**QLoRA 4-bit (this model)**", q)}

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
| Modal container, 2 vCPU / 4 GB | {min(m_ms)/1000:.1f} – {max(m_ms)/1000:.1f} s (7 hand-written logs) |
| Laptop, Celeron N4500, 2 cores, no AVX | {min(l_ms)/1000:.1f} – {max(l_ms)/1000:.1f} s |
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
@misc{{chheda2026oncallai,
  title  = {{OnCall AI: Intelligent Production Incident Analyzer -- QLoRA incident classifier}},
  author = {{Chheda, Rachit Manish}},
  year   = {{2026}},
  url    = {{https://github.com/rachitst/oncall-ai}}
}}
```
"""
out = sys.argv[2]
open(out, "w").write(card)
print("wrote", out, len(card), "chars")
