# FreshCart Pipelines

FreshCart Pipelines is a small, practical data engineering project that brings together three common patterns in modern analytics work: a machine learning data pipeline, a full ELT workflow for sales data, and a lightweight streaming event-processing example.

Instead of focusing on one narrow script, the repository is structured like a real-world data platform playground where different pieces of the pipeline can be developed, tested, and reasoned about independently.

## What this project includes

### 1. Iris machine learning pipeline
The `iris_project` folder contains a minimal pipeline for working with the Iris dataset. It demonstrates the typical steps of a data science/data engineering workflow:

- loading the dataset
- preparing and splitting it into train/test sets
- creating a pipeline structure using metadata-driven blocks
- training and evaluating a model

This part is intentionally simple, but it shows the core idea behind building reusable data transformations that can later scale into production pipelines.

### 2. FreshCart ELT pipeline
The `elt` folder implements an end-to-end ELT process for e-commerce-style business data. It ingests data from multiple sources, stores raw files in a landing area, loads them into Snowflake, and applies transformation logic in SQL.

The pipeline covers:

- extracting data from web/mobile/CRM/FX sources
- writing raw JSON landing files
- loading raw files into Snowflake bronze tables
- cleaning and deduplicating orders
- building customer dimension history
- enriching orders with FX and pincode data
- running data-quality checks before publishing gold-layer results

This is a good example of the ELT mindset: keep raw data untouched, separate storage from transformation, and let downstream analytics use trusted curated layers.

### 3. Streaming message flow demo
The `stream` folder contains a RabbitMQ-based example to simulate an event-driven system. It includes:

- a dispatcher that publishes messages to a topic exchange
- consumer drivers that subscribe to specific patterns
- validation logic to reject invalid messages missing required fields
- a simple demonstration of routing, filtering, and message handling

This helps illustrate how asynchronous systems can route data to different consumers based on message characteristics.

## Repository structure

```text
freshcart-pipelines/
├── elt/
│   ├── extract.py
│   ├── mock_data.py
│   ├── run_pipeline.py
│   ├── snowflake_io.py
│   └── ...
├── iris_project/
│   ├── data_loaders/
│   ├── transformers/
│   ├── pipelines/
│   ├── data_exporters/
│   └── ...
├── stream/
│   ├── dispatcher.py
│   └── driver.py
├── tests/
│   └── test_prepare_data.py
├── .github/workflows/
├── requirements.txt
├── README.md
└── ...
```

## Why this project is useful

This project is useful because it shows how data engineering work happens across multiple layers:

- data acquisition and ingestion
- transformation and validation
- analytics and reporting
- event-driven architecture
- model-ready data preparation

It is designed to feel practical and approachable, not abstract. The code is intentionally modular and easy to follow, which makes it a strong foundation for learning or extending into a larger real-world data platform.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

2. Run the test suite:

```bash
pytest
```

The project includes a focused unit test for the Iris data preparation step, which checks that the dataset is split into the expected train/test proportions.

## Running the ML pipeline example

The Iris example is a lightweight demonstration of data preparation and model workflow. The relevant steps are organized under `iris_project/` and rely on pandas and scikit-learn.

## Running the ELT workflow

The ELT flow in `elt/` is designed to be run from the project root. It supports both mock data and real external sources.

Examples:

```bash
cd elt
python run_pipeline.py --setup --mock
python run_pipeline.py --mock
python run_pipeline.py --dry-run --mock
```

For real integrations, you would supply the required environment variables and Snowflake credentials in a `.env` file or deployment environment.

## Running the streaming demo

The stream example uses RabbitMQ. Start a RabbitMQ broker locally, then run the dispatcher and one or more consumer drivers:

```bash
python stream/dispatcher.py
python stream/driver.py bangalore "*.koramangala.*"
```

This demonstrates message routing, queue binding, and message validation in an asynchronous pipeline.

## Tools and technologies used

- Python
- pandas
- scikit-learn
- pytest
- Snowflake SQL and connectors
- RabbitMQ + pika
- JSON-based landing files and ELT patterns

## Summary

FreshCart Pipelines is a compact but realistic collection of data engineering examples that cover the entire journey from raw data to processed outputs. It combines classic data preparation, warehouse-based transformation, and event-driven processing in one place, making it a useful project for learning, experimentation, and future extension.

The repository is intentionally structured to show how simple building blocks can evolve into more complete production-style pipelines without becoming overly complex.
