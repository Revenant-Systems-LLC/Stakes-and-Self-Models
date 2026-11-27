# 012 Which Mythos models can the Clawlings key call?

Anthropic API: yes
Runner: -m runner.list_models --probe

Replaces job 008, which stopped because it had no key. David asked for this check with the key he put in the vault. It lists the models the key can see (free), then sends one tiny message to claude-mythos-5-2 and one to claude-mythos-5-1 to confirm the organization is cleared to call each. Expected cost is under $0.05. Settles which Mythos goes into the exploratory tiers.
