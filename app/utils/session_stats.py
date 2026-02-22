import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

@dataclass
class ModelUsage:
    requests: int = 0
    input_tokens: int = 0
    cache_reads: int = 0
    output_tokens: int = 0

    def get_cost(self, model: str) -> float:
        # Very rough estimates for OpenRouter/Popular models (per 1M tokens)
        costs = {
            "gpt-4o": (5.0, 15.0),
            "claude-3-5-sonnet": (3.0, 15.0),
            "deepseek-v3": (0.14, 0.28),
            "deepseek-r1": (0.55, 2.19),
            "llama-3": (0.05, 0.1),
        }
        
        # Default fallback
        price_in, price_out = 1.0, 3.0
        
        model_lower = model.lower()
        for k, (pin, pout) in costs.items():
            if k in model_lower:
                price_in, price_out = pin, pout
                break
        
        return (self.input_tokens * price_in / 1_000_000) + (self.output_tokens * price_out / 1_000_000)

@dataclass
class SessionStats:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    tool_calls_total: int = 0
    tool_calls_success: int = 0
    tool_calls_failure: int = 0
    
    user_agreements_total: int = 0
    user_agreements_reviewed: int = 0
    
    lines_added: int = 0
    lines_removed: int = 0
    
    model_usage: Dict[str, ModelUsage] = field(default_factory=dict)
    
    api_time: float = 0.0
    tool_time: float = 0.0

    def get_total_stats(self) -> dict:
        total_input = 0
        total_output = 0
        total_cost = 0.0
        for model, usage in self.model_usage.items():
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_cost += usage.get_cost(model)
        
        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "cost": total_cost
        }

    def record_tool_call(self, success: bool = True):
        self.tool_calls_total += 1
        if success:
            self.tool_calls_success += 1
        else:
            self.tool_calls_failure += 1

    def record_api_call(self, model: str, input_tokens: int, output_tokens: int, duration: float, cache_reads: int = 0):
        if model not in self.model_usage:
            self.model_usage[model] = ModelUsage()
        
        u = self.model_usage[model]
        u.requests += 1
        u.input_tokens += input_tokens
        u.output_tokens += output_tokens
        u.cache_reads += cache_reads
        self.api_time += duration

    def record_tool_execution(self, duration: float):
        self.tool_time += duration

    def record_code_changes(self, added: int, removed: int):
        self.lines_added += added
        self.lines_removed += removed

    def record_user_agreement(self, reviewed: bool = True):
        self.user_agreements_total += 1
        if reviewed:
            self.user_agreements_reviewed += 1

    def finalize(self):
        self.end_time = time.time()

    def print_summary(self):
        self.finalize()
        console = Console()
        
        wall_time = self.end_time - self.start_time
        agent_active = self.api_time + self.tool_time
        
        # Tool call success rate
        success_rate = (self.tool_calls_success / self.tool_calls_total * 100) if self.tool_calls_total > 0 else 0
        agreement_rate = (self.user_agreements_reviewed / self.user_agreements_total * 100) if self.user_agreements_total > 0 else 100.0
        
        summary_text = Text()
        summary_text.append("Agent powering down. Goodbye!\n\n", style="bold green")
        
        summary_text.append("Interaction Summary\n", style="bold cyan")
        summary_text.append(f"Session ID:                 {self.session_id}\n")
        
        tool_status = f"✓ {self.tool_calls_success} x {self.tool_calls_failure}"
        summary_text.append(f"Tool Calls:                 {self.tool_calls_total} ({tool_status})\n")
        summary_text.append(f"Success Rate:               {success_rate:.1f}%\n")
        summary_text.append(f"User Agreement:             {agreement_rate:.1f}% ({self.user_agreements_reviewed} reviewed)\n")
        summary_text.append(f"Code Changes:               +{self.lines_added} -{self.lines_removed}\n")
        
        total_cost = sum(u.get_cost(m) for m, u in self.model_usage.items())
        summary_text.append(f"Total Cost:                 ${total_cost:.4f}\n\n")
        
        summary_text.append("Performance\n", style="bold cyan")
        summary_text.append(f"Wall Time:                  {self.format_duration(wall_time)}\n")
        summary_text.append(f"Agent Active:               {self.format_duration(agent_active)}\n")
        
        api_percent = (self.api_time / agent_active * 100) if agent_active > 0 else 0
        tool_percent = (self.tool_time / agent_active * 100) if agent_active > 0 else 0
        
        summary_text.append(f"  » API Time:               {self.format_duration(self.api_time)} ({api_percent:.1f}%)\n")
        summary_text.append(f"  » Tool Time:              {self.format_duration(self.tool_time)} ({tool_percent:.1f}%)\n\n")
        
        summary_text.append("Model Usage\n", style="bold cyan")
        
        table = Table(box=None, header_style="bold", padding=(0, 2))
        table.add_column("Model")
        table.add_column("Reqs", justify="right")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Cache Reads", justify="right")
        table.add_column("Output Tokens", justify="right")
        table.add_column("Cost", justify="right")
        
        total_input = 0
        total_cache = 0
        for model, usage in self.model_usage.items():
            cost = usage.get_cost(model)
            table.add_row(
                model, 
                str(usage.requests), 
                f"{usage.input_tokens:,}", 
                f"{usage.cache_reads:,}", 
                f"{usage.output_tokens:,}",
                f"${cost:.4f}"
            )
            total_input += usage.input_tokens
            total_cache += usage.cache_reads
            
        console.print(Panel(summary_text, border_style="blue", padding=(1, 2)))
        if self.model_usage:
            console.print(table)
            if total_cache > 0:
                cache_percent = (total_cache / (total_input + total_cache) * 100) if (total_input + total_cache) > 0 else 0
                console.print(f"\nSavings Highlight: {total_cache:,} ({cache_percent:.1f}%) of input tokens were served from the cache, reducing costs.", style="italic dim")

    @staticmethod
    def format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        m, s = divmod(seconds, 60)
        return f"{m:.0f}m {s:.0f}s"

# Global instance for easy access
session_tracker = SessionStats()
