from agent_platform.worker.sandbox_process import _context_policy_patch


def test_context_policy_patch_matches_validated_dsh_rc1_policy() -> None:
    patch = _context_policy_patch(
        context_window=4096,
        max_output_tokens=1024,
    )

    assert patch == (
        "- id: llm-deepseek\n"
        "  config:\n"
        "    apiKeyEnv: DEEPSEEK_API_KEY\n"
        "    defaultContextWindow: 4096\n"
        "    maxTokens: 1024\n"
        "    streamIdleTimeoutMs: 172800000\n"
        "\n"
        "- insert:\n"
        "    - id: token-meter\n"
        "      name: '@deepseek-ai/dsh-token-meter'\n"
        "\n"
        "    - id: compaction-basic\n"
        "      name: '@deepseek-ai/dsh-compaction-basic'\n"
        "      config:\n"
        "        thresholdRatio: 0.55\n"
        "        retainTokens: 1024\n"
        "        maxTokens: 768\n"
        "        compactionRetries: 1\n"
        "        maxOverflowRetries: 1\n"
        "        auto: true\n"
    )

    assert "headroomTokens" not in patch
