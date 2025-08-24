# Genetic Health Analysis Toolkit

This is a comprehensive genetic data analysis platform with the following setup:

## Project Structure
- **Backend**: FastAPI with UV package management
- **Frontend**: Next.js with TypeScript and Tailwind CSS
- **Analysis**: Genetic data processing for VCF and CSV files

## Development Commands
- Backend: `cd backend && PYTHONPATH=.. uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- Frontend: `cd frontend && npm run dev`
- Use VS Code tasks: "Start Backend Server", "Start Frontend Dev Server", or "Start Both Servers"

## URLs
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## Features
- VCF and CSV file upload and analysis
- Health risk assessment dashboard
- Drug response pharmacogenomic analysis
- Interactive data visualization
- Privacy-focused local processing

All project setup tasks have been completed successfully.

- [x] Clarify Project Requirements
	<!-- Genetic health analysis toolkit with UV, FastAPI backend, Next.js frontend for VCF/CSV analysis -->

- [ ] Scaffold the Project
	<!--
	Ensure that the previous step has been marked as completed.
	Call project setup tool with projectType parameter.
	Run scaffolding command to create project files and folders.
	Use '.' as the working directory.
	If no appropriate projectType is available, search documentation using available tools.
	Otherwise, create the project structure manually using available file creation tools.
	-->

- [ ] Customize the Project
	<!--
	Verify that all previous steps have been completed successfully and you have marked the step as completed.
	Develop a plan to modify codebase according to user requirements.
	Apply modifications using appropriate tools and user-provided references.
	Skip this step for "Hello World" projects.
	-->

- [ ] Install Required Extensions
	<!-- ONLY install extensions provided mentioned in the get_project_setup_info. Skip this step otherwise and mark as completed. -->

- [ ] Compile the Project
	<!--
	Verify that all previous steps have been completed.
	Install any missing dependencies.
	Run diagnostics and resolve any issues.
	Check for markdown files in project folder for relevant instructions on how to do this.
	-->

- [ ] Create and Run Task
	<!--
	Verify that all previous steps have been completed.
	Check https://code.visualstudio.com/docs/debugtest/tasks to determine if the project needs a task. If so, use the create_and_run_task to create and launch a task based on package.json, README.md, and project structure.
	Skip this step otherwise.
	 -->

- [ ] Launch the Project
	<!--
	Verify that all previous steps have been completed.
	Prompt user for debug mode, launch only if confirmed.
	 -->

- [ ] Ensure Documentation is Complete
	<!--
	Verify that all previous steps have been completed.
	Verify that README.md and the copilot-instructions.md file in the .github directory exists and contains current project information.
	Clean up the copilot-instructions.md file in the .github directory by removing all HTML comments.
	 -->