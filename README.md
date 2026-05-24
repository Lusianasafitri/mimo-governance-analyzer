# MiMo Governance Analyzer

DAO governance proposal analysis and voting pattern tracker. Built with **MiMo V2.5**.

## Features

- Proposal analysis (approval rate, quorum, sentiment, risk)
- Voter behavior tracking and profiling
- Whale concentration detection
- SQLite persistence for historical analysis
- Risk assessment for proposals

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# View summary
python analyzer.py --summary

# Analyze specific proposal
python analyzer.py --proposal MIP-001

# Analyze voter behavior
python analyzer.py --voter 0x1234...

# Custom DAO name
python analyzer.py --dao "My DAO" --summary
```

## License

MIT
