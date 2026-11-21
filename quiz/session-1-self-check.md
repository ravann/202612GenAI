# Session 1 Self-Check Quiz: The LLM as a System Component

**Format:** 10 questions, about 10 minutes. Unlimited retries, not graded, nothing submitted. 

---

**Q1.** A 20% daily cost overrun appears after a prompt grows by 3,000 tokens of fixed preamble that is identical on every call. Which lever applies first?
- A. Raise the temperature
- B. Cache the stable prefix (prompt caching)
- C. Raise `max_tokens`
- D. Switch from streaming to non-streaming

**Q2.** Your code reads the answer with `resp.content[0].text`. On Sonnet 5.5 it sometimes fails or returns the wrong block. Why, and what is the fix?
- A. The model is non-deterministic, so retry the call
- B. A `thinking` block can come before the `text` block. Join the blocks whose `type` is `"text"`
- C. `content` is a string, not a list
- D. Raise `max_tokens` so the first block is always text

**Q3.** Time to first token is good, but users complain that long answers feel slow. What do you measure next?
- A. Output tokens per second and total latency
- B. Input token count only
- C. The temperature setting
- D. The number of SDK retries

**Q4.** In the Session 1 scripts you move bulk work from Sonnet 5.5 to Haiku 5.5. What must change?
- A. The system prompt and the streaming loop
- B. The `MODEL` constant and its `PRICES` entry, and nothing else
- C. The `temperature`, set lower for the cheaper model
- D. The history format

**Q5.** A model-produced ticket ID does not exist in the CMDB. Where should the check live?
- A. In the prompt ("never invent IDs")
- B. In your code, against the system of record, after the model answers
- C. In a lower temperature
- D. In a bigger model

**Q6.** The Messages API is stateless. To make the model "remember" turn 1 in turn 3 you must:
- A. Set a session ID header
- B. Resend the conversation history in each request
- C. Enable prompt caching
- D. Increase `max_tokens`

**Q7.** You need more consistent output from Sonnet 5.5, and you try `temperature=0`. What happens, and what is the right response?
- A. It works and output becomes identical on every call
- B. It is rejected: the SDK has no `temperature` argument (a `TypeError`), and the API returns HTTP 400 for `temperature`, `top_p` and `top_k` on every current model, so you measure run-to-run variation (k runs per case) instead of dialling it out
- C. It is silently ignored, so nothing needs to change
- D. It only works if you also set `max_tokens`

**Q8.** Which formula is the per-call cost model?
- A. total tokens x one blended price
- B. input tokens x input price + output tokens x output price, with discounts for cached input and batch
- C. output tokens x output price only
- D. a flat price per request

**Q9.** Which error is worth retrying with backoff and jitter?
- A. 401 authentication failure
- B. 400 invalid request
- C. 429 rate limit
- D. A request that exceeds the context window

**Q10.** Where does an API key belong?
- A. In `models.yaml` committed to Git
- B. In an environment variable or git-ignored `.env`, as an org-provisioned key with a spend limit
- C. In the system prompt
- D. In the JSONL log for traceability

---

## Answer key

1. **B.** A fixed prefix repeated on every call is exactly what caching discounts.
2. **B.** Content is a list of typed blocks. Thinking comes before text, so select text blocks by type.
3. **A.** Streaming changes perceived latency, not throughput or total latency.
4. **B.** The model ID and price are the only model-specific facts in the file. A missing price shows up as `cost unknown` in the footer and `null` in the log, never as a wrong number. Sampling settings do not exist to carry over.
5. **B.** Semantic checks belong in code against the source of truth, not in a prompt.
6. **B.** The API is stateless. The application owns the state.
7. **B.** The installed SDK has no sampling arguments (a `TypeError` before anything is sent), and the current API version rejects them on every model with a 400. Variation is a property you measure in evals (Session 3), not a setting.
8. **B.** Input and output are priced separately, with cache and batch discounts.
9. **C.** Rate limits are transient. 401, 400 and over-context errors will not fix themselves.
10. **B.** Keep secrets out of the repo, prompts and logs. Use spend-limited keys.
