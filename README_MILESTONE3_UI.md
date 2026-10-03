# Milestone 3 UI - Interview Assistance & ATS Integration

The `/interview` page now presents the three Milestone 3 capabilities together, following the supplied reference layout:

1. **Role-specific interview question generator**
   - Select a job role and question type.
   - Generates role-specific recruiter questions from the existing 15-role question bank.
   - Candidate practice remains separate through `/candidate-interview` and uses the configured 50% competency-overlap policy.

2. **AI interview simulation**
   - Select a candidate.
   - Start the generated interview in the chat panel.
   - Submit answers and receive automated evaluation for score, technical relevance, communication and structure.
   - The existing optional LLM evaluator remains available through the configured AI API for the full candidate practice submission flow.

3. **ATS integration**
   - Candidate cards are displayed directly below the interview panels.
   - Test the built-in Demo ATS connection.
   - Select one or more candidates and synchronize them through `/api/ats/sync`.
   - Demo ATS records are persisted in `data/mock_ats_candidates.json`.
   - External REST ATS configuration remains available on `/ats`.

## Demo flow

`/interview` -> select role -> Generate Questions -> select candidate -> answer interview questions -> review automated evaluation -> select candidates -> Sync Selected Candidates.
