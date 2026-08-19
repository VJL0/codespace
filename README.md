# CodeSpace

CodeSpace is a real-time classroom coding platform designed to help teachers monitor, support, and interact with students while they code.

Students can join a classroom and work in browser-based coding environments, while teachers can view student activity, manage sessions, and provide help without constantly moving between computers.

> **Status:** CodeSpace is currently under active development.

## Why I Built It

I came up with CodeSpace while thinking about how I would teach programming if I became a lead instructor for Temple University's STEM Scholars summer program, which works with middle school students.

As a computer science student and software developer, I wanted a better way to manage a classroom where every student is coding at the same time. It can be difficult for an instructor to see who is stuck, understand what students are working on, and provide help without constantly walking between computers.

After researching the problem further, I found other programming instructors and teachers online describing similar challenges. That made me realize this was not just a problem I might face in my own classroom, so I decided to keep building CodeSpace into something that could be useful beyond my own teaching experience.

The goal is to give instructors a central place to monitor student coding sessions, manage the classroom, and help students in real time while keeping the experience simple for students.

CodeSpace started as a tool I wanted for my own classroom and has grown into an attempt to solve a broader problem in teaching programming.

## Features

* Real-time classroom coding experience
* Browser-based coding environment for students
* Teacher dashboard for monitoring student activity
* Classroom creation and management
* Student access through classroom codes
* Role-based permissions for teachers and students
* Backend code execution
* Authentication and session management
* Real-time communication between clients and the server

More classroom-management and collaboration features are currently in development.

## Tech Stack

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* Apollo Client

### Backend

* Python
* FastAPI
* GraphQL
* SQLAlchemy
* PostgreSQL
* WebSockets

### Infrastructure

* Docker
* Docker Compose
* Alembic

## Architecture

CodeSpace uses a full-stack architecture with a React frontend and Python backend.

The backend is structured so API logic, business logic, and data access remain separated as the application grows.

```text
Frontend
   |
   | GraphQL / WebSockets
   v
FastAPI Backend
   |
   |-- Resolvers
   |-- Services
   |-- Repositories
   |-- Models
   |
   v
PostgreSQL
```

## Project Structure

```text
codespace/
├── frontend/          # React + TypeScript frontend
├── backend/           # FastAPI backend
├── docker-compose.yml
└── README.md
```

## Running Locally

### Requirements

* Node.js
* Python
* Docker
* Docker Compose

Clone the repository:

```bash
git clone https://github.com/VJL0/codespace.git
cd codespace
```

Start the required services:

```bash
docker compose up
```

Additional frontend and backend setup instructions can be found in their respective directories.

## What I'm Working On

Current development is focused on:

* Improving the live classroom experience
* Expanding teacher classroom controls
* Improving real-time student monitoring
* Building a better browser-based coding environment
* Improving code execution and session management
* Making it easier for students to join and start coding

## What I Want to Explore

CodeSpace combines several areas of software engineering that I am particularly interested in:

* Developer tools
* Education technology
* Real-time applications
* Backend architecture
* Collaborative coding environments
* Making programming more accessible

I want to continue exploring how better developer tooling can make programming easier to teach, learn, and collaborate on.

## Author

Built by [Victor Jimenez-Lorenzo](https://github.com/VJL0).
