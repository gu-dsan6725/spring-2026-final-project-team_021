## Schemas

This folder contains the data formats used across the project.

Instead of passing around raw dictionaries, we define structured schemas so that all agents and pipeline stages follow the same format.

### What’s inside

- **Analyst schemas**  
  Define the output format for technical and fundamental agents (e.g., signal, confidence, summary, factors).

- **Debate & judge schemas**  
  Define how bull and bear arguments are structured, as well as the final decision from the judge agent.

### Why this matters

This is a multi-agent system, so different components depend on each other's outputs.  
These schemas make sure everything stays consistent and prevent mismatched fields or broken pipelines.
