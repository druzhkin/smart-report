from backend.agents.research_agent import _parse_citations


def test_parse_citations_handles_openrouter_url_citation_annotations() -> None:
    raw_response = {
        "choices": [
            {
                "message": {
                    "content": "Example content with citation markers.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url_citation": {
                                "url": "https://www.bvp.com/atlas/the-ai-pricing-and-monetization-playbook",
                                "title": "The AI Pricing and Monetization Playbook",
                            },
                        },
                        {
                            "type": "url_citation",
                            "url_citation": {
                                "url": "https://www.alphasense.com/blog/market-intelligence/what-is-market-intelligence/",
                                "title": "Market intelligence platform overview | AlphaSense",
                            },
                        },
                    ],
                }
            }
        ]
    }

    sources = _parse_citations(raw_response)

    assert len(sources) == 2
    assert sources[0].url == "https://www.bvp.com/atlas/the-ai-pricing-and-monetization-playbook"
    assert sources[0].title == "The AI Pricing and Monetization Playbook"
    assert sources[1].domain == "www.alphasense.com"
