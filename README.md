# Genetic Health Analysis Toolkit

A comprehensive genetic data analysis platform built with FastAPI backend and Next.js frontend. This toolkit allows users to upload genetic data (VCF/CSV files) and receive personalized health insights, risk assessments, and drug response information.

## Features

- **Genetic Data Processing**: Upload and analyze VCF and CSV genetic data files
- **Health Risk Assessment**: Get personalized health risk scores for various conditions
- **Drug Response Analysis**: Pharmacogenomic insights for medication optimization
- **Interactive Dashboard**: Visualize genetic data with charts and comprehensive reports
- **Modern UI**: Clean, responsive interface built with Next.js and Tailwind CSS
- **Secure Processing**: Local data processing with privacy-focused design

## Technology Stack

### Backend
- **FastAPI**: High-performance Python web framework
- **UV**: Modern Python package management
- **BioPython**: Biological sequence analysis
- **Pandas/NumPy**: Data processing and analysis
- **Pydantic**: Data validation and serialization

### Frontend
- **Next.js 15**: React framework with App Router
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first CSS framework
- **Recharts**: Data visualization components
- **Lucide React**: Modern icon library

## Project Structure

```
dna_toolkit/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── genetic_analyzer.py  # Core genetic analysis
│   ├── vcf_parser.py        # VCF file processing
│   ├── health_insights.py   # Health risk assessment
│   └── drug_response.py     # Pharmacogenomic analysis
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js app directory
│   │   └── components/      # React components
│   └── package.json
├── pyproject.toml           # Python dependencies
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.11+ with UV package manager
- Node.js 18+ with npm

### Installation

1. **Clone and setup the project**:
   ```bash
   cd dna_toolkit
   ```

2. **Install Python dependencies**:
   ```bash
   uv install
   ```

3. **Install frontend dependencies**:
   ```bash
   cd frontend
   npm install
   ```

### Running the Application

1. **Start the FastAPI backend**:
   ```bash
   uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Start the Next.js frontend** (in a new terminal):
   ```bash
   cd frontend
   npm run dev
   ```

3. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Usage

1. **Upload Genetic Data**: 
   - Drag and drop VCF or CSV files onto the upload area
   - Supported formats: `.vcf` (Variant Call Format), `.csv` (genetic data)

2. **View Analysis Results**:
   - Overview: Summary statistics and key metrics
   - Health Risks: Risk assessment for various health conditions
   - Drug Response: Pharmacogenomic insights and recommendations
   - Recommendations: Personalized health and lifestyle suggestions

3. **Interpret Results**:
   - Results are for informational purposes only
   - Always consult healthcare professionals for medical decisions
   - Consider genetic counseling for complex findings

## API Endpoints

### File Upload
- `POST /upload/vcf` - Upload VCF files
- `POST /upload/csv` - Upload CSV genetic data

### Analysis
- `GET /analyze/health-insights/{rsid}` - Get insights for specific variants
- `GET /analyze/drug-response/{gene}` - Get drug response for genes
- `POST /analyze/full-report` - Generate comprehensive analysis

### Search
- `GET /variants/search` - Search variants by gene/chromosome/position

## Data Privacy & Security

- **Local Processing**: All data is processed locally on your machine
- **No Data Storage**: Genetic data is not permanently stored
- **Privacy First**: Designed with genetic privacy principles in mind
- **Secure Communication**: HTTPS recommended for production use

## Genetic Data Sources Supported

- **VCF Files**: Standard variant call format from genetic testing
- **CSV Files**: Genetic data exports from services like:
  - 23andMe
  - AncestryDNA
  - MyHeritage
  - Other genetic testing services

## Health Conditions Analyzed

- Cardiovascular disease risk
- Type 2 diabetes susceptibility
- Cancer predisposition
- Neurological conditions
- Athletic performance traits
- Drug metabolism profiles

## Drug Response Analysis

Pharmacogenomic analysis for genes including:
- CYP2D6, CYP2C19, CYP2C9 (drug metabolism)
- DPYD, TPMT (chemotherapy sensitivity)
- SLCO1B1 (statin response)
- And many more...

## Development

### Backend Development
```bash
# Run with auto-reload
uv run uvicorn backend.main:app --reload

# Run tests (when implemented)
uv run pytest

# Type checking
uv run mypy backend/
```

### Frontend Development
```bash
cd frontend

# Development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Disclaimer

**Important**: This toolkit is for educational and research purposes. Genetic information should always be interpreted by qualified healthcare professionals. Do not use this tool for medical diagnosis or treatment decisions.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions, issues, or feature requests, please open an issue on the project repository.

## Acknowledgments

- Built with modern web technologies and bioinformatics libraries
- Inspired by the need for accessible genetic data analysis tools
- Designed with privacy and user control in mind
