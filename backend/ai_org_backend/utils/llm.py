import backoff, openai

@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat(model: str, messages: list[dict], **kw):
    return openai.ChatCompletion.create(model=model, messages=messages, **kw)

@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat_completion(prompt: str, model: str = "gpt-3.5-turbo", **kw) -> str:
    resp = openai.ChatCompletion.create(model=model, messages=[{"role": "user", "content": prompt}], **kw)
    return resp.choices[0].message.content
