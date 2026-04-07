# Open-source coding models for self-hosted assistants: Decision Brief

## Executive Summary

Open-source coding models for self-hosted assistants: coverage 1/3 primary questions, 5 recommendation-safe claims, contradiction count 0.

## Decision Context

- Goal: Produce an evidence-backed analytical report for a real decision.
- Subject: Open-source coding models for self-hosted assistants
- Decision context: Choose a primary platform for a production pilot in the next two quarters.
- Geography: global
- Time horizon: current

## Evaluation Frame

- code quality
- deployment flexibility
- licensing
- cost

## Key Findings

- Qwen2.5-Coder is described as an open-weight coding family with multilingual support and agent-style workflow fit. [Evidence: b05d7a58-2800-465c-88b4-c5c6efdd1cec, 2584376c-3e8c-44da-bb44-b1067a3ca636]
- In a coding-model evaluation it should not replace task-specific testing, but it is valuable for checking whether vendor claims are directionally supported by repeated public eval performance. [Evidence: 18bc366f-bc9e-4065-8bbe-93caaafae93a]
- It is attractive when coding capability matters, but deployment flexibility and licensing need careful review in a self-hosted decision. [Evidence: 3649fcd9-350d-4bbc-a603-4d71e5f9043e, 4a7fc688-2df9-445a-8192-000bea9fb15b]
- Its main upside is flexible self-hosting with community adoption. [Evidence: 607d8be8-1475-4847-a506-fa5773f8e990, de32dc01-5b62-487d-824a-e9314a2f67bb]
- The main tradeoff is the need to validate quality and efficiency on the buyer's own workloads. [Evidence: 25c5c1a2-87c9-45ad-8d99-9257e393d88d, 4381924f-8990-43da-9ce9-2d37c163657f]

## Comparative Analysis

- Which options are truly self-hostable?
- Which models show the strongest public coding signal?
- What are the main quality versus operations tradeoffs?

## Recommendation and Decision Posture

- Bounded recommendation: evidence is informative but not strong enough for an unqualified winner call.

## Gaps & Risks

- Which models show the strongest public coding signal?
- What are the main quality versus operations tradeoffs?
- Prefer pragmatic operating cost and privacy-aware deployment.

## Evidence Coverage

- Covered questions: 1/3
- Contradiction count: 0

## Sources

- [LiveBench leaderboard](https://livebench.ai/)
- [Codestral launch](https://mistral.ai/news/codestral/)
- [Qwen2.5-Coder family](https://qwenlm.github.io/blog/qwen2.5-coder-family/)
