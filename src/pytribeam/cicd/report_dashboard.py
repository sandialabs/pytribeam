#!/usr/bin/env python3
"""
Generates the root index.html Project Dashboard for GitHub Pages.
"""

import argparse
import os

from pytribeam.cicd.utilities import (
    ReportMetadata,
    add_common_args,
    extend_timestamp,
    report_metadata_creation,
)


def generate_dashboard_html(metadata: ReportMetadata) -> str:
    """
    Generate the HTML content for the Project Dashboard using a two-column layout.

    Args:
        metadata: CI/CD metadata

    Returns:
        HTML string
    """
    timestamp_ext = extend_timestamp(metadata.timestamp)

    # Pre-calculate GitHub URLs to stay under line length limits
    github_url = f"https://github.com/{metadata.github_repo}"
    run_url = f"{github_url}/actions/runs/{metadata.run_id}"
    branch_url = f"{github_url}/tree/{metadata.ref_name}"
    commit_url = f"{github_url}/commit/{metadata.github_sha}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>pyTriBeam | Project Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        // Tailwind config for dark mode support
        tailwind.config = {{
            darkMode: 'class',
        }}
        
        // Check for saved theme preference or system preference
        if (localStorage.getItem('theme') === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
            document.documentElement.classList.add('dark')
        }} else {{
            document.documentElement.classList.remove('dark')
        }}

        function toggleDarkMode() {{
            if (document.documentElement.classList.contains('dark')) {{
                document.documentElement.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            }} else {{
                document.documentElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }}
        }}
    </script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; }}
        .hover-card:hover {{ transform: translateY(-2px); transition: all 0.2s ease; }}
    </style>
</head>
<body class="bg-slate-50 text-slate-800 antialiased min-h-screen dark:bg-[#0d1117] dark:text-[#c9d1d9] transition-colors duration-300">
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-50 dark:bg-[#010409] dark:border-[#30363d]">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
            <div class="flex items-center gap-4">
                <span class="text-xl font-bold tracking-tight text-blue-600 dark:text-blue-400">pyTriBeam</span>
                <button onclick="toggleDarkMode()" class="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:ring-2 ring-slate-300 transition-all">
                    <span class="dark:hidden">🌙</span>
                    <span class="hidden dark:inline">☀️</span>
                </button>
            </div>
            <a href="{github_url}" class="text-sm font-medium hover:text-blue-600 dark:hover:text-blue-400 transition">GitHub Repository</a>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <header class="mb-12 text-center">
            <h1 class="text-4xl font-extrabold tracking-tight text-slate-900 dark:text-[#f0f6fc] mb-4">
                <b>Project Dashboard</b>
            </h1>
            <p class="text-lg text-slate-600 dark:text-[#8b949e] max-w-2xl mx-auto">
                Access documentation and quality reports for pyTriBeam.
            </p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <section class="space-y-6">
                <div class="flex items-center justify-between border-b-2 border-blue-200 dark:border-blue-900 pb-2">
                    <h2 class="text-2xl font-bold flex items-center gap-2">🚀 Released</h2>
                </div>
                <div class="space-y-4">
                    <a href="main/book/jupyter/index.html"
                       class="hover-card block p-5 bg-white dark:bg-[#161b22] rounded-xl shadow-sm border border-slate-200 dark:border-[#30363d] hover:border-blue-600 dark:hover:border-blue-400 group">
                        <div class="flex justify-between items-start">
                            <div>
                                <h3 class="font-bold text-lg group-hover:text-blue-600 dark:group-hover:text-blue-400">User's Manual</h3>
                                <p class="text-sm text-slate-500 dark:text-[#8b949e] mt-1">Stable documentation for end-users.</p>
                            </div>
                        </div>
                    </a>
                    </div>
            </section>
            
            </div>

        <section class="mt-16 bg-white dark:bg-[#0d1117] p-8 rounded-xl shadow-sm border border-slate-200 dark:border-[#30363d]">
            <h2 class="text-xl font-bold mb-4 border-b dark:border-[#30363d] pb-2 text-slate-900 dark:text-[#f0f6fc]">Build Metadata</h2>
            </section>
    </main>
    </body>
</html>"""


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Project Dashboard index.html"
    )
    parser.add_argument("--output_file", required=True, help="Output HTML file path")

    add_common_args(parser)

    args = parser.parse_args()

    metadata = report_metadata_creation(args)

    html = generate_dashboard_html(metadata)

    output_dir = os.path.dirname(args.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] Project Dashboard generated: {args.output_file}")


if __name__ == "__main__":
    main()
