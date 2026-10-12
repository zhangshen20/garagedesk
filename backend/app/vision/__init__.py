"""Job card photo -> job draft.

The owner writes job cards on paper and will not type. He photographs the card
with his iPhone; a vision model on Nebius Token Factory reads the handwriting,
NVIDIA Nemotron 3 Super turns that reading into a clean job draft, and every field
carries a confidence so the owner app can read back only what it is unsure of.
Token Factory has no Nemotron vision model, hence the split."""
