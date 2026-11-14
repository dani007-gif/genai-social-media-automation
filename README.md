# genai-social-media-automation
Email-driven, multi-LLM pipeline that turns a customer’s request into a brand-aligned social media post and publishes it automatically through MCP tool calling. Containerized with Docker and Kubernetes, with CI/CD on GitHub.

# Applied GenAI – Social Media Handling

An end-to-end generative AI system that automates social media posting. A customer sends
an email describing the post they want. A chain of specialised LLM stages extracts the
requirements, brainstorms ideas, picks the best one, writes the post, publishes it via
MCP, and replies to the customer once it is live.

## How it works

1. **Input (email)**: the customer's request arrives by email.
2. **LLM 1, KPI extraction**: the email is parsed into structured requirements:
   - post size / format
   - company name and logo (including logo placement)
   - post theme
   - must-have, nice-to-have and not-to-have elements
   - whether similar posts already exist (for reference)
3. **LLM 2, idea generation**: a strong system prompt takes the KPIs and generates 4–5 post ideas (text).
4. **LLM 3, selection**: scores each idea for relevance against the KPIs and chooses the best one.
5. **LLM 4, post generation**: writes the final post from the selected idea.
6. **MCP tool calling**: the post is published to the company's social media account through an MCP server.
7. **Confirmation**: a reply email is sent to the customer after the post is live.

## Tech stack

- **LLM / VLM**: separate models for extraction, ideation, scoring and generation
- **MCP (Model Context Protocol)**: tool calling to the social media account
- **Docker**: containerized services
- **Kubernetes**: orchestration and deployment
- **Cloud**: hosting
- **CI/CD**: GitHub (Actions) for build, test and deploy

## Key design ideas

- **Multi-stage LLM chain**: each stage has one job, which makes outputs easier to debug and improve.
- **Structured KPIs as the contract** between stages, so generated posts stay on-brief.
- **Generate-then-select**: producing several ideas and scoring them for relevance improves quality over a single-shot post.
- **Human-free loop**: from inbound email to published post to customer confirmation.
