require('dotenv').config();
const express = require('express');
const path = require('path');
const api = require('../routes/api');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));
app.use('/api', api);

app.use((err, req, res, next) => {
  const detail = err.response ? err.response.data : err.message;
  console.error(detail);
  res.status(err.response ? err.response.status : 500).json({ error: detail });
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Server listening at http://localhost:${port}`));
