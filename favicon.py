from main.responses import FileResponse

@app.get("/favicon.ico", include_in=False)
async def favicon():
    return FileResponse("favicon.ico")