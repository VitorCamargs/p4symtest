# References for LLM warning system

## P4 verification and testing

- p4v: Practical Verification for Programmable Data Planes. DOI: `10.1145/3230543.3230582`.
- ASSERT-P4: Uncovering Bugs in P4 Programs with Assertion-based Verification. DOI: `10.1145/3185467.3185499`.
- p4pktgen: Automated Test Case Generation for P4 Programs.
- P4Testgen: An Extensible Test Oracle for P4-16. DOI: `10.1145/3603269.3604834`.

## LLM context, hallucination, and RAG

- OpenAI, "Why language models hallucinate": https://openai.com/research/why-language-models-hallucinate/
- OpenAI Help, "Retrieval Augmented Generation (RAG) and Semantic Search for GPTs": https://help.openai.com/en/articles/8868588-retrieval-augmented-generation-rag-and-semantic-search-for-gpts
- Anthropic, "Long context prompting tips": https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips
- Anthropic, "Reduce hallucinations": https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations
- Google Gemini API, "Long context": https://ai.google.dev/gemini-api/docs/long-context
- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", TACL 2024. DOI: `10.1162/tacl_a_00638`.

## Local open-source model and runtime references

- Qwen2.5-Coder-7B-Instruct model card: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct
- Qwen2.5-Coder-3B-Instruct model card: https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct
- llama.cpp repository and server runtime: https://github.com/ggml-org/llama.cpp
- Qdrant documentation: https://qdrant.tech/documentation/

## Notes for article writing

The article should position the LLM as a semantic interpreter over symbolic evidence, not as a replacement for formal verification. The RAG discussion should emphasize curated evidence, reproducibility, and the limits of long context windows.

