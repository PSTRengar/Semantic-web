
⸻

Smart Academic Advisor – Semantic Web Prototype

This project is a functional Semantic Web application prototype built for the
II.3521 – Semantic Web and Knowledge Management course.

It integrates:
	•	an OWL ontology,
	•	heterogeneous CSV data sources,
	•	a Knowledge Graph built at runtime,
	•	SPARQL querying,
	•	explainable recommendations (courses, careers, papers),
	•	and a simple Web interface.

⸻

1. Requirements
	•	Python ≥ 3.9 (tested with Python 3.11 / 3.13)
	•	macOS / Linux / Windows
	•	Internet connection (only for installing dependencies)

⸻

2. Installation

Step 1 – Unzip / clone the project

cd path/to/your/workspace
unzip s2a_prototype.zip
cd s2a_prototype

(or git clone if applicable)

⸻

Step 2 – Create a virtual environment (recommended)

python3 -m venv .venv

Activate it:
	•	macOS / Linux:

source .venv/bin/activate

	•	Windows:

.venv\Scripts\activate


⸻

Step 3 – Install dependencies

pip install -r requirements.txt


⸻

3. Run the application

python app.py

You should see:

Running on http://127.0.0.1:5000


⸻

4. Use the application
	1.	Open a browser
	2.	Go to:
👉 http://127.0.0.1:5000

You can:
	•	select a student profile,
	•	see personalized course/career/paper recommendations,
	•	inspect explainable recommendation paths,
	•	run SPARQL queries,
	•	use predefined SPARQL query templates.

⸻

5. Ontology (Protégé)

The file:

s2a_semantic_recommender.owl

can be opened directly with Protégé to inspect:
	•	classes,
	•	object properties,
	•	datatype properties,
	•	individuals.

The ontology is instantiated and used at runtime by the Python application.

⸻

6. Notes
	•	The system automatically builds the Knowledge Graph from CSV files at startup.
	•	No database or external triple store is required.
	•	This is a development prototype, not a production deployment.

⸻

End of README
