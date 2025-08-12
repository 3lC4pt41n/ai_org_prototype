import re


def strip_code_fences(code: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = code.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text


def infer_extension(code: str) -> str:
    """Heuristically determine file extension based on code content."""
    text = code.strip()
    text_lower = text.lower()
    if ("export " in text and "function " in text) or "import " in text_lower:
        if "<" in text and ">" in text and (
            "react" in text_lower or re.search(r"return\s+<", text_lower)
        ):
            return ".tsx"
        if text.lstrip().startswith("<"):
            return ".html"
        if re.search(r"\b(?:interface|enum|:\s*[\w\[\]|]+\s*=)", text):
            return ".ts"
        return ".ts"
    if "<" in text and (text_lower.count("<div") or text_lower.count("<html")):
        return ".html"
    if re.search(r"\.[\w-]+\s*{", text):
        return ".css"
    return ".py"
