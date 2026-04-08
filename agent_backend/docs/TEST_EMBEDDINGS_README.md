# Bedrock Titan Embeddings Test

## Overview
This test script (`test_bedrock_embeddings.py`) demonstrates how AWS Bedrock Titan embeddings work and calculates similarity scores to understand vector search behavior.

## What it does

1. **Loads AWS credentials** from your `.env` file (via boto3 session)
2. **Generates embeddings** for multiple test sentences using AWS Bedrock Titan model
3. **Calculates cosine similarity** between query and sentences
4. **Shows which sentences would match** in a vector search based on:
   - Absolute threshold: 0.15 (minimum similarity score)
   - Percentile threshold: 0.7 (top 70% of max score)

## How to run

```bash
cd /home/popo/work/work/trelloOpen/mcp_gmail
python test_bedrock_embeddings.py
```

## Prerequisites

1. **AWS Credentials**: Must be configured (via `~/.aws/credentials` or environment variables)
2. **Environment Variables**: `.env` file should exist (for other configs)
3. **Dependencies**: Already in `requirements.txt`:
   - boto3
   - botocore
   - numpy
   - python-dotenv
   - requests

## Test Cases Included

### Test Case 1: Meeting-related sentences
- Query: "Find emails about scheduling team meetings"
- Tests: Various meeting-related sentences vs unrelated content

### Test Case 2: Project-related sentences
- Query: "Show me project status updates"
- Tests: Project updates vs unrelated content

### Test Case 3: Mixed unrelated sentences
- Query: "Security issues and system alerts"
- Tests: Security-related vs social/unrelated content

## Understanding the Output

### Similarity Scores
- Range: -1 to 1 (typically 0 to 1 for positive correlation)
- Higher score = more similar
- Example scores:
  - 0.8-1.0: Very similar (strong match)
  - 0.5-0.8: Moderately similar (good match)
  - 0.15-0.5: Somewhat similar (weak match)
  - Below 0.15: Not similar (filtered out)

### Match Criteria
A sentence MUST pass BOTH thresholds to appear in vector search results:

1. **Absolute threshold** (0.15): Minimum similarity score
2. **Percentile threshold** (70% of max): Relative to best match

### Sample Output
```
Rank 1: Similarity = 0.7523 ✓ MATCH
  Text: Schedule a meeting with the team for tomorrow at 3pm

Rank 2: Similarity = 0.6891 ✓ MATCH
  Text: Meeting agenda: Q4 goals, team updates, and action items

Rank 3: Similarity = 0.3245 ✗ FILTERED OUT (below percentile threshold)
  Text: Book a conference room for the quarterly planning session

Rank 4: Similarity = 0.1123 ✗ FILTERED OUT (below absolute threshold)
  Text: The weather is nice today, let's go for a walk
```

## How This Relates to Your Codebase

This test mimics the exact behavior used in:
- `clients/mongo_email_client.py` - Email vector search
- `clients/mongo_context_client.py` - Context retrieval
- `clients/mongo_calendar_client.py` - Calendar event search
- `clients/mongo_docs_client.py` - Document search
- `clients/mongo_notion_client.py` - Notion page search

All these clients use the same:
- AWS Bedrock Titan embedding model (`amazon.titan-embed-text-v2:0`)
- 1024-dimensional embeddings
- Cosine similarity calculation
- Dual threshold filtering (absolute + percentile)

## Customizing Tests

You can modify the script to test your own sentences:

```python
# Add your own test case
custom_sentences = [
    "Your sentence 1",
    "Your sentence 2",
    "Your sentence 3",
]

custom_query = "Your search query"

test_embeddings_and_similarity(custom_sentences, custom_query)
```

## Troubleshooting

### AWS Credentials Error
```
Error: Unable to locate credentials
```
**Solution**: Configure AWS credentials:
```bash
aws configure
# OR set environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

### Bedrock Access Error
```
Error: Could not connect to the endpoint URL
```
**Solution**: Ensure you have access to AWS Bedrock in `us-east-1` region

### Dimension Mismatch Warning
```
WARNING: Expected 1024 dimensions, got 768
```
**Solution**: This indicates the model returned unexpected dimensions. Check model ID is correct.

## Key Insights

1. **Semantic similarity**: Embeddings capture meaning, not just keywords
2. **Context matters**: "Book a meeting" vs "Book a table" - different contexts
3. **Threshold tuning**: Adjust thresholds based on your use case:
   - Higher absolute threshold (e.g., 0.3) → More precise, fewer results
   - Lower absolute threshold (e.g., 0.1) → More recall, more noise
4. **Percentile filtering**: Ensures only top results relative to best match

## References

- [AWS Bedrock Titan Embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)
- [Cosine Similarity](https://en.wikipedia.org/wiki/Cosine_similarity)
- Vector Search in MongoDB: Used in all `clients/mongo_*_client.py` files







