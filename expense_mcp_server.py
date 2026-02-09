#!/usr/bin/env python3
"""
MCP Server for Expense Report Generator API

This MCP server provides tools to generate expense reports from receipt images
through the FastAPI backend.

Installation:
    pip install mcp requests

Usage:
    # Start the FastAPI server first
    python app.py
    
    # Then run this MCP server
    python mcp_server.py

Configuration for Claude Desktop (add to claude_desktop_config.json):
{
  "mcpServers": {
    "expense-report": {
      "command": "python",
      "args": ["/path/to/mcp_server.py"],
      "env": {
        "EXPENSE_API_URL": "http://localhost:8000"
      }
    }
  }
}
"""

import json
import os
import base64
from pathlib import Path
from typing import Any
import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Configuration
API_BASE_URL = os.environ.get("EXPENSE_API_URL", "http://localhost:8000")


def encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to base64 string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


async def generate_expense_report(
    image_paths: list[str],
    employee_id: str,
    employee_name: str,
    manager_name: str,
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
) -> dict[str, Any]:
    """
    Generate expense report by calling the FastAPI backend.
    
    Args:
        image_paths: List of paths to receipt images
        employee_id: Employee ID
        employee_name: Employee name
        manager_name: Reporting manager name
        model: Groq model to use for extraction
        
    Returns:
        Dictionary with success status, download URL, and filename
    """
    
    # Validate image files exist
    for img_path in image_paths:
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Image file not found: {img_path}")
    
    # Prepare multipart form data
    files = []
    for img_path in image_paths:
        files.append(
            ('images', (Path(img_path).name, open(img_path, 'rb'), 'image/jpeg'))
        )
    
    data = {
        'employee_id': employee_id,
        'employee_name': employee_name,
        'manager_name': manager_name,
        'model': model
    }
    
    try:
        # Call the API
        response = requests.post(
            f"{API_BASE_URL}/generate-report",
            files=files,
            data=data,
            timeout=300  # 5 minutes timeout for processing
        )
        
        # Close file handles
        for _, file_tuple in files:
            file_tuple[1].close()
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "download_url": f"{API_BASE_URL}{result['download_url']}",
                "filename": result['filename'],
                "message": f"Expense report generated successfully! Download at: {API_BASE_URL}{result['download_url']}"
            }
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            return {
                "success": False,
                "error": f"API returned status {response.status_code}: {error_detail}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out. The report generation may be taking longer than expected."
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Could not connect to API at {API_BASE_URL}. Make sure the FastAPI server is running."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


# Create MCP server instance
app = Server("expense-report-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="generate_expense_report",
            description="""Generate an expense report from receipt images using AI.

This tool processes receipt/bill images and extracts expense information to create 
a formatted Excel expense report. It uses the Groq API with vision models to analyze 
receipts and extract details like invoice numbers, dates, amounts, vendor names, etc.

The tool:
1. Accepts multiple receipt images (up to any number - automatically batched)
2. Extracts expense data using AI vision model
3. Generates a formatted Excel (.xlsx) file with:
   - Employee information header
   - Expense line items with columns: Serial No, Document Number, Date, 
     Description, Vendor Name, Bill Provided, Amount
   - Automatic total calculation using Excel formulas

The report can be downloaded from the returned URL.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to receipt/bill images (JPG, PNG, GIF, WebP)"
                    },
                    "employee_id": {
                        "type": "string",
                        "description": "Employee ID (e.g., 'E12345')"
                    },
                    "employee_name": {
                        "type": "string",
                        "description": "Full name of the employee"
                    },
                    "manager_name": {
                        "type": "string",
                        "description": "Full name of the reporting manager"
                    },
                    "model": {
                        "type": "string",
                        "description": "Groq model to use for extraction (default: meta-llama/llama-4-scout-17b-16e-instruct)",
                        "default": "meta-llama/llama-4-scout-17b-16e-instruct"
                    }
                },
                "required": ["image_paths", "employee_id", "employee_name", "manager_name"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    
    if name == "generate_expense_report":
        image_paths = arguments.get("image_paths", [])
        employee_id = arguments.get("employee_id")
        employee_name = arguments.get("employee_name")
        manager_name = arguments.get("manager_name")
        model = arguments.get("model", "meta-llama/llama-4-scout-17b-16e-instruct")
        
        # Validate required parameters
        if not image_paths:
            return [TextContent(
                type="text",
                text="Error: No image paths provided. Please specify at least one receipt image path."
            )]
        
        if not employee_id or not employee_name or not manager_name:
            return [TextContent(
                type="text",
                text="Error: Missing required fields. Please provide employee_id, employee_name, and manager_name."
            )]
        
        # Generate the report
        result = await generate_expense_report(
            image_paths=image_paths,
            employee_id=employee_id,
            employee_name=employee_name,
            manager_name=manager_name,
            model=model
        )
        
        # Format response
        if result.get("success"):
            response_text = f"""✅ Expense Report Generated Successfully!

📊 Report Details:
- Filename: {result['filename']}
- Processed Images: {len(image_paths)}
- Employee: {employee_name} (ID: {employee_id})
- Manager: {manager_name}
- Model Used: {model}

📥 Download URL: {result['download_url']}

The report includes:
- Employee information header
- Detailed expense line items from all receipts
- Automatic total calculation

You can download the Excel file from the URL above."""
        else:
            response_text = f"""❌ Failed to Generate Expense Report

Error: {result.get('error', 'Unknown error occurred')}

Please check:
1. The FastAPI server is running at {API_BASE_URL}
2. All image file paths are correct and accessible
3. The GROQ_API_KEY environment variable is set
4. Image files are in supported formats (JPG, PNG, GIF, WebP)"""
        
        return [TextContent(type="text", text=response_text)]
    
    else:
        return [TextContent(
            type="text",
            text=f"Error: Unknown tool '{name}'"
        )]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())