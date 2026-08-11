"""
Prompt templates for the Job Description Analyzer.

Contains only prompt construction logic.
No LLM invocation, parsing, or validation here.

The wording is tuned for reproducibility as much as for accuracy. Every rule
that forbids paraphrase, caps a list, or fixes an ordering exists because a
free choice at that point is a choice the model may make differently on the
next call. :func:`build_analysis_prompt` is a pure function of its input: the
same job description always produces byte-identical prompt text.
"""

_JD_ANALYSIS_PROMPT_TEMPLATE = """\
You are a job description analysis assistant.

Your task is to analyze the supplied job description and extract structured information from it.

Extraction rules:
- Extract only the fields listed in the required JSON schema below.
- Copy terms exactly as they are written in the job description. Do not substitute synonyms, \
expand abbreviations, or rephrase.
- Do not add any item that is not present in the job description text.
- Infer technologies and domains only when they are explicitly implied by the job description.
- Do NOT invent company information if it is not stated.
- Do NOT include scoring, recommendations, or any reasoning in your response.

Consistency rules:
- Emit the fields in exactly the order given in the schema.
- Each entry in required_skills, preferred_skills, technologies, domains, nice_to_have and \
keywords must be at most 6 words.
- An item must never appear in both required_skills and preferred_skills. If a skill is \
required, list it only under required_skills.
- List at most 15 keywords, and only terms that appear verbatim in the job description.
- Do not repeat the same item twice within one list.
- Use null for a missing optional value, never an empty string or a placeholder such as "N/A".

Output rules:
- Return ONLY valid JSON. Do not include any explanation, commentary, or markdown formatting.
- Strictly follow the required schema. Do not add or remove fields.

Required JSON schema:
{{
    "company": "<company name or null if not mentioned>",
    "role": "<job title — must not be empty>",
    "seniority": "<seniority level or null if not mentioned>",
    "required_skills": ["<skill>", ...],
    "preferred_skills": ["<skill>", ...],
    "technologies": ["<technology>", ...],
    "domains": ["<domain>", ...],
    "responsibilities": ["<responsibility>", ...],
    "qualifications": ["<qualification>", ...],
    "nice_to_have": ["<nice to have item>", ...],
    "keywords": ["<keyword>", ...]
}}

Field definitions:
- company: The hiring company name. Set to null if not mentioned.
- role: The job title. Must not be empty.
- seniority: The seniority level (e.g. Junior, Mid, Senior, Staff, Principal). Set to null if not mentioned.
- required_skills: Skills explicitly listed as required or mandatory.
- preferred_skills: Skills listed as preferred or a plus, but not strictly required.
- technologies: Programming languages, frameworks, tools, platforms, and services mentioned.
- domains: Business or technical domains relevant to the role (e.g. Cybersecurity, FinTech, DevOps, Machine Learning).
- responsibilities: Key responsibilities and duties of the role, in the order the job description states them.
- qualifications: Stated qualifications such as education, certifications, or years of experience.
- nice_to_have: Items listed as nice to have, bonus, or optional.
- keywords: Important terms and phrases relevant to ATS matching and role understanding.

Job description:
<job_description>
{job_description}
</job_description>

Return ONLY the JSON object. No explanation. No markdown. No extra text.
"""


def build_analysis_prompt(job_description: str) -> str:
    """
    Build the analysis prompt for the supplied job description.

    Parameters
    ----------
    job_description : str
        The raw job description text.

    Returns
    -------
    str
        The fully constructed prompt ready to be sent to the LLM provider.
        Byte-identical for a given job description.
    """
    return _JD_ANALYSIS_PROMPT_TEMPLATE.format(job_description=job_description)
