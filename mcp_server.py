from mcp.server.fastmcp import FastMCP 
mcp = FastMCP('report-server')

@mcp.tool()
def read_report() -> str:
    """Read and return the contents of report.txt"""
    with open('report.txt') as bur:
        return bur.read()

if __name__ == "__main__":
      mcp.run()