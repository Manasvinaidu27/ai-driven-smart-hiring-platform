# Interview module fix

- 40 recruiter questions are guaranteed for every job and selected question type.
- Generate Questions uses the Flask API and a browser-side role/skill fallback.
- AI simulation starts at Question 1 automatically after generation.
- Send evaluates, saves the answer, displays feedback, advances one question at a time, and shows a final score.
- Fixed missing `timezone` import used by answer persistence.
- Browser cache version bumped.
