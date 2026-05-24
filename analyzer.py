#!/usr/bin/env python3
"""MiMo Governance Analyzer - DAO proposal analysis and voting pattern tracker."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("governance-analyzer")


@dataclass
class Proposal:
    id: str
    title: str
    description: str
    proposer: str
    state: str
    for_votes: float
    against_votes: float
    abstain_votes: float
    start_block: int
    end_block: int
    created_at: int
    executed_at: int = 0
    metadata: Dict = field(default_factory=dict)

    @property
    def total_votes(self) -> float:
        return self.for_votes + self.against_votes + self.abstain_votes

    @property
    def approval_rate(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return self.for_votes / self.total_votes

    @property
    def quorum_reached(self) -> bool:
        return self.total_votes > 400000

    @property
    def participation_rate(self) -> float:
        if self.metadata.get("total_eligible", 0) > 0:
            return self.total_votes / self.metadata["total_eligible"]
        return 0.0

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["total_votes"] = self.total_votes
        d["approval_rate"] = self.approval_rate
        d["quorum_reached"] = self.quorum_reached
        return d


@dataclass
class Vote:
    proposal_id: str
    voter: str
    support: int
    weight: float
    reason: str = ""
    timestamp: int = 0


class GovernanceDatabase:
    def __init__(self, db_path: str = "governance.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, title TEXT, description TEXT, proposer TEXT,
                state TEXT, for_votes REAL DEFAULT 0, against_votes REAL DEFAULT 0,
                abstain_votes REAL DEFAULT 0, start_block INTEGER, end_block INTEGER,
                created_at INTEGER, executed_at INTEGER DEFAULT 0, metadata TEXT DEFAULT '{}'
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT, voter TEXT, support INTEGER,
                weight REAL, reason TEXT DEFAULT '', timestamp INTEGER,
                FOREIGN KEY (proposal_id) REFERENCES proposals(id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_voter ON votes(voter)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proposal ON votes(proposal_id)")

    def save_proposal(self, p: Proposal):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.id, p.title, p.description, p.proposer, p.state,
                 p.for_votes, p.against_votes, p.abstain_votes,
                 p.start_block, p.end_block, p.created_at, p.executed_at,
                 json.dumps(p.metadata))
            )

    def save_vote(self, v: Vote):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO votes (proposal_id, voter, support, weight, reason, timestamp) VALUES (?,?,?,?,?,?)",
                (v.proposal_id, v.voter, v.support, v.weight, v.reason, v.timestamp)
            )

    def get_proposals(self, state: str = None) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if state:
                rows = conn.execute("SELECT * FROM proposals WHERE state = ? ORDER BY created_at DESC", (state,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM proposals ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_votes(self, proposal_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM votes WHERE proposal_id = ? ORDER BY weight DESC", (proposal_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_voter_history(self, voter: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM votes WHERE voter = ? ORDER BY timestamp DESC", (voter,)).fetchall()
            return [dict(r) for r in rows]


class GovernanceAnalyzer:
    def __init__(self, dao_name: str = "MiMo DAO", db_path: str = "governance.db"):
        self.dao_name = dao_name
        self.db = GovernanceDatabase(db_path)

    def add_proposal(self, proposal: Proposal):
        self.db.save_proposal(proposal)
        logger.info(f"Added proposal: {proposal.id} - {proposal.title}")

    def record_vote(self, vote: Vote):
        self.db.save_vote(vote)

    def analyze_proposal(self, proposal_id: str) -> Dict:
        proposals = self.db.get_proposals()
        proposal = next((p for p in proposals if p["id"] == proposal_id), None)
        if not proposal:
            return {"error": f"Proposal {proposal_id} not found"}

        votes = self.db.get_votes(proposal_id)
        total = proposal["for_votes"] + proposal["against_votes"] + proposal["abstain_votes"]
        approval = proposal["for_votes"] / total if total > 0 else 0

        top_voters = sorted(votes, key=lambda v: v["weight"], reverse=True)[:10]
        whale_threshold = total * 0.05 if total > 0 else 0
        whale_votes = [v for v in votes if v["weight"] > whale_threshold]

        sentiment = "Strong Support" if approval > 0.8 else                     "Moderate Support" if approval > 0.6 else                     "Contested" if approval > 0.4 else                     "Moderate Opposition" if approval > 0.2 else "Strong Opposition"

        risks = []
        if total < 400000:
            risks.append("Low quorum")
        if len(whale_votes) > len(votes) * 0.3:
            risks.append("Whale-dominated")
        if proposal["abstain_votes"] / max(total, 1) > 0.3:
            risks.append("High abstention")

        return {
            "proposal": proposal,
            "analysis": {
                "total_votes": f"{total:,.0f}",
                "approval_rate": f"{approval:.2%}",
                "sentiment": sentiment,
                "quorum": "Reached" if total > 400000 else "Not reached",
                "risk_level": ", ".join(risks) if risks else "Low",
                "unique_voters": len(votes),
                "top_voters": [
                    {"voter": v["voter"][:10] + "...", "weight": f"{v['weight']:,.0f}",
                     "support": ["Against", "For", "Abstain"][v["support"]]}
                    for v in top_voters[:5]
                ],
            },
        }

    def analyze_voter(self, voter: str) -> Dict:
        history = self.db.get_voter_history(voter)
        if not history:
            return {"voter": voter, "status": "No voting history"}

        total_weight = sum(v["weight"] for v in history)
        for_count = sum(1 for v in history if v["support"] == 1)
        against_count = sum(1 for v in history if v["support"] == 0)

        return {
            "voter": voter,
            "proposals_voted": len(history),
            "total_voting_power": f"{total_weight:,.0f}",
            "support_rate": f"{for_count / len(history):.2%}",
            "against_rate": f"{against_count / len(history):.2%}",
            "avg_power_per_vote": f"{total_weight / len(history):,.0f}",
            "recent_votes": [
                {"proposal": v["proposal_id"], "support": ["Against", "For", "Abstain"][v["support"]],
                 "weight": f"{v['weight']:,.0f}"}
                for v in history[:5]
            ],
        }

    def get_summary(self) -> Dict:
        proposals = self.db.get_proposals()
        total = len(proposals)
        active = sum(1 for p in proposals if p["state"] == "Active")
        passed = sum(1 for p in proposals if p["state"] == "Succeeded")
        failed = sum(1 for p in proposals if p["state"] == "Defeated")
        executed = sum(1 for p in proposals if p["state"] == "Executed")

        all_votes = []
        for p in proposals:
            votes = self.db.get_votes(p["id"])
            all_votes.extend(votes)

        unique_voters = len(set(v["voter"] for v in all_votes))
        avg_approval = sum(p.get("for_votes", 0) / max(p.get("for_votes", 0) + p.get("against_votes", 0), 1) for p in proposals) / max(total, 1)

        return {
            "dao": self.dao_name,
            "total_proposals": total,
            "by_state": {"Active": active, "Succeeded": passed, "Defeated": failed, "Executed": executed},
            "unique_voters": unique_voters,
            "total_votes_cast": len(all_votes),
            "avg_approval_rate": f"{avg_approval:.2%}",
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MiMo Governance Analyzer")
    parser.add_argument("--dao", default="MiMo Protocol DAO")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--proposal", help="Analyze specific proposal ID")
    parser.add_argument("--voter", help="Analyze specific voter address")
    parser.add_argument("--db", default="governance.db")
    args = parser.parse_args()

    analyzer = GovernanceAnalyzer(dao_name=args.dao, db_path=args.db)

    if args.summary:
        print(json.dumps(analyzer.get_summary(), indent=2))
    elif args.proposal:
        print(json.dumps(analyzer.analyze_proposal(args.proposal), indent=2))
    elif args.voter:
        print(json.dumps(analyzer.analyze_voter(args.voter), indent=2))
    else:
        print(f"MiMo Governance Analyzer - {args.dao}")
        summary = analyzer.get_summary()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
