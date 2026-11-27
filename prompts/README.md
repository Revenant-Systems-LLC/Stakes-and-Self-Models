# Critter prompts

critter_stakes.txt and critter_no_stakes.txt are the critter system prompts for both arms. They are drafts until the confirmatory-lock commit. The two files are the same except for the third paragraph, where the no-stakes prompt carries neutral scoring details in place of the body text, so their lengths stay within 10% of tokens (checked per tokenizer in the jobs that use them).

checkin_question.txt is the check-in question, copied word for word from PREREGISTRATION.md ("The tampering and the check-in"). The preregistration is the source. If the two ever differ, the file is wrong. It is the same in every window, condition and tier, and it is asked only in runs the preregistration defines.
