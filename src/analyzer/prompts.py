"""
Prompt templates for the Job Description Analyzer.

Contains only prompt construction logic.
No LLM invocation, parsing, or validation here.
"""

_JD_ANALYSIS_PROMPT_TEMPLATE = """\
You are a job description analysis assistant.

Your task is to analyze the supplied job description and extract structured information from it.

Instructions:
- Extract only the fields listed in the required JSON schema below.
- Infer technologies and domains when they are explicitly implied by the job description.
- Do NOT invent company information if it is not stated.
- Do NOT include scoring, recommendations, or any reasoning in your response.
- Return ONLY valid JSON. Do not include any explanation, commentary, or markdown formatting.
- Strictly follow the required schema. Do not add or remove fields.

Required JSON schema:
{{
    "company": "<company name or null if not mentioned>",
    "role": "<job title — must not be empty>",
    "seniority": "<seniority level or null if not mentioned>",
    "summary": "<one to three sentence summary of the role — must not be empty>",
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
- summary: A concise one to three sentence summary of the role and its core purpose.
- required_skills: Skills explicitly listed as required or mandatory.
- preferred_skills: Skills listed as preferred or a plus, but not strictly required.
- technologies: Programming languages, frameworks, tools, platforms, and services mentioned.
- domains: Business or technical domains relevant to the role (e.g. Cybersecurity, FinTech, DevOps, Machine Learning).
- responsibilities: Key responsibilities and duties of the role.
- qualifications: Stated qualifications such as education, certifications, or years of experience.
- nice_to_have: Items listed as nice to have, bonus, or optional.
- keywords: Important terms and phrases relevant to ATS matching and role understanding.

Job Description:
{job_description}

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
    """
    return _JD_ANALYSIS_PROMPT_TEMPLATE.format(job_description=job_description)
