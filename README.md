# MedGemma Kaggle

A clinical communication system powered by locally served MedGemma models. See [clinical-agents/README.md](clinical-agents/README.md) 
and [clinical-agents-bot/README.md](clinical-agents-bot/README.md) for full documentation.

## Summary of capabilities

- Patient message intake and intent classification
- Automatic escalation for red-flag symptoms (chest pain, stroke signs, respiratory distress)
- LLM tool calling to retrieve patient EHR data and clinical knowledge
- Clinical case card generation with QA safety gates
- Staff review and approval workflow
- Patient-facing reply generation in Traditional Chinese
- JWT authentication with role-based access control
- Audit logging of all database writes
- RAG pipeline for clinical SOPs and protocols

---

## Model Weights

The following directories store locally cached model weights and are not tracked by version control:

| Directory | Contents |
|-----------|----------|
| `medgemma-bf16/` | MedGemma 1.5 4B in BF16 |
| `medgemma-fp8/` | MedGemma 1.5 4B quantized to FP8 |
| `embedgemma/` | Embedgemma embedding model |
| `routergemma/` | Gemma 3 router model |
