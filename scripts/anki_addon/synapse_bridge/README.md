# Synapse native review bridge

`bridge.py` contains the scheduler operation used by the AnkiConnect action
`synapseAnswerCard`. The operation must be registered in the installed
AnkiConnect add-on so that its HTTP handler calls:

```python
from synapse_bridge.bridge import answer_card
result = answer_card(mw, params["cardId"], params["ease"])
```

The registration is intentionally kept separate from Synapse's Python
environment: Anki loads add-ons from its own profile and provides `mw`.
