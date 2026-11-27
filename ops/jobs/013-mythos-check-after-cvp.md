# 013 Recheck Mythos access after CVP is added to the Clawlings workspace

Anthropic API: yes
Runner: -m runner.list_models --probe

Same check as 012. In 012 the Clawlings key got HTTP 404 not_found_error for claude-mythos-5-2 and claude-mythos-5-1, and neither showed in its model list. Anthropic's docs say a 404 means the model isn't available to the organization, and Mythos is limited to verified programs such as CVP. David is assigning his CVP grant to the Clawlings workspace and making a new key that expires within 7 days (Defense Access rule until December 15, 2026), stored in the same vault, A:\env\Clawlings.dpapi. The watcher decrypts the vault fresh for each job, so this run uses the new key. Run it only after the new key is in the vault. Expected cost under $0.05.
