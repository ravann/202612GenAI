**The idea for learning:** the original file shows idempotency, scopes, confirmation and a write cap all at once. Here they come in order, as a ladder. **The riskier the write, the further the decision moves from the model:**

| Risk | Who decides | Example |
|---|---|---|
| Read | Nobody; it just runs | search incidents |
| Write | The person who asked says yes, now | assign an incident |
| High-risk change | A different person with authority, later | fail over a database |

| File | Concept | What happened when I ran it |
|---|---|---|
| [1_direct_write.py](src/s4/3_safe_writes/1_direct_write.py) | A write changes things for everyone, at once (no model). | INC-0030 moved from erin to dave. |
| [2_model_writes.py](src/s4/3_safe_writes/2_model_writes.py) | A model with a write tool and no checks. | "Give all the printer incidents to dave" changed **5 records** with nobody asked. That included erin's in-progress ticket and one that was already resolved. |
| [3_confirm_gate.py](src/s4/3_safe_writes/3_confirm_gate.py) | Step 2 plus a gate in `dispatch()`. Every write shows a person the exact call and asks y/N. | I answered no to 2 of the 5 calls. Those two weren't changed, and the model's answer said so. |
| [4_retry_safe.py](src/s4/3_safe_writes/4_retry_safe.py) | Step 1's code with `intent_key()` added: a retried create (no model). | Retrying with no key created two incidents (INC-0043, INC-0044) for one broken printer. With a key made from the request, the retry returned INC-0043 again. |

Files 2 and 3 are the same except for the gate (about 15 lines), so diffing them shows the whole idea. Step 3 asks for y/N in the terminal, so run it yourself rather than piping input. If nobody is at the keyboard, the answer counts as no.


