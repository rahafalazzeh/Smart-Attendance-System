const express = require("express");
const app = express();

app.post("/recognize", (req, res) => {
  res.json({ 
    found: true, 
    x: Math.random() * 200, 
    y: Math.random() * 120 
  });
});

app.listen(3000, () => console.log("Mock Server running on http://localhost:3000"));