# NOURA — Where Surplus Finds Purpose

> NOURA is an AI-powered food redistribution platform that connects surplus food from event organizers with suitable recipient organizations, helping good food reach the right place at the right time instead of going to waste.

## Team

**Team Name:** AIgnite



---

# Problem Statement

## The Problem

Large events such as college fests, conferences, weddings, and corporate gatherings often prepare food based on estimated attendance. When fewer people attend than expected, a significant amount of prepared food can remain unused.

At the same time, NGOs, community kitchens, shelters, and other local organizations may be able to make use of these meals.

The problem is not always the lack of food or the lack of organizations willing to receive it. The real challenge is **connecting available surplus food with the right recipient quickly enough**.

Today, this process can depend on manual calls, messages, searching for organizations, and coordinating pickup between multiple people. This becomes especially difficult when the food is available only for a limited period.

## Why We Chose This Problem

We chose this problem because food waste and the need for food can exist at the same time, while the connection between them can still be inefficient.

Surplus food from an event can become difficult to redistribute simply because the right recipient is not identified quickly.

We wanted to build a solution around a simple idea:

> **If good food is available, it should have a chance to reach someone who can use it.**

NOURA aims to make that connection faster, more structured, and easier to coordinate.

---

# Solution

NOURA is a platform that connects **food donors** with **recipient organizations** through a structured information and matching workflow.

The donor provides information about the available surplus food, while the receiver provides information about their organization, capacity, requirements, and availability.

The system evaluates the information from both sides and uses an AI-assisted matching process to identify suitable connections.

A **volunteer or NGO acts as the coordination layer**, helping connect the donor and receiver and facilitating the redistribution process.

For the Hack Day prototype, NOURA is implemented as a local **Streamlit application** that demonstrates this complete workflow.

## Key Features

- **Donor Information:** Collects information about the event, available food, quantity, location, preparation time, dietary details, and availability.
- **Receiver Information:** Collects organization details, location, capacity, food requirements, and availability.
- **AI-Assisted Matching:** Uses an open-weight AI model to assist in identifying suitable donor–receiver connections.
- **Volunteer / NGO Coordination:** Provides a coordination layer between donors and receivers to help facilitate redistribution.

---

# Innovation and Differentiation

NOURA focuses on solving the **connection problem** between surplus food and organizations that can use it.

Instead of relying entirely on manual searching, phone calls, or scattered communication, NOURA structures information from both donors and receivers and uses it to assist the matching process.

The project also keeps humans involved in the process.

Volunteers and NGOs are not replaced by AI. They remain an important coordination layer that can review and facilitate the connection between the donor and receiver.

Another important aspect of NOURA is that AI is not being added simply as a chatbot. It is incorporated into the core matching workflow to help interpret donor and receiver information and provide a meaningful recommendation.

---

# Technical Implementation

## Architecture


    A[Food Donor] --> B[Donor Information]
    C[Recipient Organization] --> D[Receiver Information]

    B --> E[Streamlit Application]
    D --> E

    E --> F[Data Validation]
    F --> G[Matching Logic]

    G --> H[Open-Weight AI Model]
    H --> I[AI-Assisted Recommendation]

    I --> J[Volunteer / NGO Coordination]
    J --> K[Recipient Organization]

    J --> L[Redistribution Process]

### Technology Stack


| Category            | Technologies                                                                                                                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Frontend**        | Server-rendered HTML using **Jinja2 templates**, **CSS**, and **plain JavaScript**. **Leaflet 1.9.4** is used for interactive maps. Pages use periodic polling for live updates.                                                                                                     |
| **Backend**         | **Python** and **Flask**. Flask handles routing, form processing, matching logic, volunteer assignment, tracking, and autonomous replanning.                                                                                                                                         |
| **Database**        | **SQLite**, storing receivers, volunteers, donations, and match/assignment information.                                                                                                                                                                                              |
| **AI / ML**         | **Rule-based AI / intelligent decision system** using food compatibility, receiver capacity, actual food need, urgency/deadline, and road distance to rank matches. Automatic volunteer assignment and autonomous re-planning are also implemented. No trained ML model is required. |
| **Infrastructure**  | Runs locally using the **Flask development server** at `127.0.0.1:5000`. Built primarily with open-source technologies.                                                                                                                                                              |
| **APIs / Services** | **OpenStreetMap** for map data, **Nominatim** for address/geocoding, **OSRM** for road distance and route calculation, **Leaflet** for map visualization, and **Google Maps Directions** links for navigation.                                                                       |



If a category or technology is not implemented in the project, specify `N/A` instead of leaving the field blank.

### How It Works

[Explain the major components of the system and how they interact.]

### Technical Decisions

[Explain important architectural, algorithmic, or engineering decisions made during development.]

## Implementation During the Hackathon


| Member            | Contribution |
| ------------------| ------------ |
| B Aswin           | Project architecture, application logic, AI integration, GitHub and documentation |
| C B Arunvanan     | AI/ML integration and matching logic |
| E Sivam Pandiyan  | Streamlit interface and user experience |
| Pragadeeshvaran R | Donor and receiver data handling, integration and testing |

## Working Application

**Live Application:** [Live URL]

[Briefly explain how the deployed application can be accessed and what functionality can be tested.]

The submitted application should be functional and accessible through the provided link where applicable.

## Demo Video

**Demo Video:** [Video URL]

[Provide a short demonstration of the working project, covering the main user flow and important functionality.]

## Open Source and AI Usage

### AI / Models

- **Google OR-Tools CP-SAT Solver**: Used as the optimization engine to intelligently split a large food donation across multiple suitable receivers while respecting constraints such as receiver capacity, minimum useful delivery size, maximum number of receivers, distance, and food availability time.
- **Rule-based food freshness model**: Estimates the safe-until window for different food categories based on preparation time. This is used to prevent the system from suggesting deliveries that are unlikely to arrive within the estimated usable window.
- **Rule-based matching score**: Ranks eligible receivers using factors such as distance, remaining food time, and receiver capacity.

### Open Source Components

- **Flask**: Python web framework used to build the FoodBridge backend and web application.
- **SQLite**: Lightweight database used to store users, donations, receivers, allocations, and delivery information.
- **Google OR-Tools**: Open-source optimization toolkit; CP-SAT is used for multi-receiver donation allocation.
- **Leaflet**: Open-source JavaScript mapping library used for interactive maps and markers.
- **OpenStreetMap**: Provides open map data and map tiles.
- **Nominatim**: OpenStreetMap-based geocoding and place-search service used for location search and reverse geocoding.
- **OSRM (Open Source Routing Machine)**: Used to calculate road routes, distances, and estimated travel times between donors, receivers, and volunteers.
- **Google Maps**: Used as an optional external directions link for users who want turn-by-turn navigation.

### Data / Datasets

- **No external training dataset is used.**
- User-created donor, receiver, volunteer, and donation data is stored in the application's SQLite database.
- Food-category freshness rules are manually defined in the application rather than learned from a dataset.

### Licenses and Attribution

FoodBridge uses open-source software and open geographic data. We retain the relevant attribution for OpenStreetMap contributors and use the respective projects according to their licenses.

- **OpenStreetMap data**: © OpenStreetMap contributors
- **Leaflet**: BSD-2-Clause
- **Google OR-Tools**: Apache License 2.0
- **Flask**: BSD-3-Clause
- **SQLite**: Public domain
- **OSRM**: BSD-2-Clause
- **Nominatim / OpenStreetMap**: OpenStreetMap project services and attribution requirements apply.

The project does not currently use a generative AI/LLM such as GPT, Qwen, Llama, or Mistral. The core AI/optimization component is the open-source OR-Tools constraint optimization system, combined with explainable rule-based matching and freshness estimation.

## Setup and Usage

### Prerequisites

- [Requirement]
- [Requirement]

### Installation

```bash
git clone [repository-url]
cd [project-directory]
[installation-command]
```

### Environment Variables

```env
[VARIABLE_NAME]=[value]
```



### Running the Project

```bash
[run-command]
```

### Usage

[Explain the basic steps required to use the project.]

## Devpost Submission

**Devpost Project:** [Devpost Project URL]

[Add the link to the team's Devpost submission. Ensure the Devpost project page is complete and contains the required project information, links, media, and team details.]

## Credits and License

### Credits

[Credit libraries, frameworks, datasets, models, APIs, contributors, and other external resources used.]

### License

[License name and/or link.]

## Submission Checklist

- [ ] Project title and description added
- [ ] All team members listed
- [ ] Problem clearly explained
- [ ] Reason for choosing the problem explained
- [ ] Solution and key features documented
- [ ] Innovation and differentiation explained
- [ ] Architecture included
- [ ] Technical implementation documented
- [ ] Work completed during the hackathon documented
- [ ] Team contributions documented
- [ ] Working application is functional
- [ ] Live application link added where applicable
- [ ] Demo video added
- [ ] AI and open-source components documented
- [ ] Setup and usage instructions tested
- [ ] Challenges and learnings documented
- [ ] Devpost submission completed
- [ ] Devpost link added
- [ ] Credits added
- [ ] License added
- [ ] Repository is organized and complete
