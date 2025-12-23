import { useState } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  // State to store the list of stocks
  const [stocks, setStocks] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [scannedCount, setScannedCount] = useState(0)

  const handleScan = async () => {
    setLoading(true)
    try {
      // Connect to your Backend
      const response = await axios.get('http://localhost:8000/scan')
      
      // Update state with the data
      setStocks(response.data.passed_stocks)
      setScannedCount(response.data.scanned_count)
    } catch (error) {
      console.error("Error fetching data:", error)
      alert("Failed to connect to backend. Is uvicorn running?")
    }
    setLoading(false)
  }

  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h1>🚀 Stock Scanner Dashboard</h1>
      
      <div style={{ marginBottom: '2rem' }}>
        <button 
          onClick={handleScan} 
          disabled={loading}
          style={{ padding: '10px 20px', fontSize: '1.2rem', cursor: 'pointer' }}
        >
          {loading ? 'Scanning...' : 'Run Scan'}
        </button>
      </div>

      {scannedCount > 0 && (
        <p>Scanned <strong>{scannedCount}</strong> stocks. Found <strong>{stocks.length}</strong> matches.</p>
      )}

      {stocks.length > 0 ? (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {stocks.map((ticker) => (
            <li 
              key={ticker} 
              style={{ 
                background: '#1a1a1a', 
                color: 'white',
                margin: '10px auto', 
                padding: '10px', 
                maxWidth: '300px',
                borderRadius: '8px' 
              }}
            >
              {ticker}
            </li>
          ))}
        </ul>
      ) : (
        !loading && scannedCount > 0 && <p>No stocks passed the filter.</p>
      )}
    </div>
  )
}

export default App