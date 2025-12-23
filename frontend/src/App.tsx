import { useState } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  // Tabs State: 'scan' or 'lookup'
  const [activeTab, setActiveTab] = useState('scan')
  
  // Scanner State
  const [scanResults, setScanResults] = useState<any[]>([])
  const [scanning, setScanning] = useState(false)

  // Lookup State
  const [tickerSearch, setTickerSearch] = useState('')
  const [stockReport, setStockReport] = useState<any>(null)
  const [lookingUp, setLookingUp] = useState(false)

  // --- HANDLERS ---
  
  const handleScan = async () => {
    setScanning(true)
    try {
      const response = await axios.get('http://localhost:8000/scan')
      setScanResults(response.data.passed_stocks)
    } catch (e) { alert("Scan failed") }
    setScanning(false)
  }

  const handleLookup = async () => {
    if (!tickerSearch) return
    setLookingUp(true)
    setStockReport(null) // Clear previous
    try {
      const response = await axios.get(`http://localhost:8000/stock/${tickerSearch}`)
      setStockReport(response.data)
    } catch (e) { 
        console.error(e)
        alert("Stock not found or DB empty") 
    }
    setLookingUp(false)
  }

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem' }}>
      <h1>📈 Algo Dashboard</h1>

      {/* TAB NAVIGATION */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button onClick={() => setActiveTab('scan')} style={{ flex: 1, background: activeTab === 'scan' ? '#646cff' : '#333' }}>
          Scanner
        </button>
        <button onClick={() => setActiveTab('lookup')} style={{ flex: 1, background: activeTab === 'lookup' ? '#646cff' : '#333' }}>
          Scorecard Lookup
        </button>
      </div>

      {/* === SCANNER TAB === */}
      {activeTab === 'scan' && (
        <div>
          <button onClick={handleScan} disabled={scanning}>
            {scanning ? 'Scanning...' : 'Run Full Scan'}
          </button>
          
          <ul style={{ marginTop: '20px', padding: 0 }}>
            {scanResults.map((item: any) => (
              <li key={item.symbol} style={{ background: '#222', padding: '10px', margin: '5px 0', borderRadius: '5px', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 'bold' }}>{item.symbol}</span>
                <span style={{ color: item.score > 70 ? '#4caf50' : '#f44336' }}>Score: {item.score}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* === LOOKUP TAB === */}
      {activeTab === 'lookup' && (
        <div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input 
              type="text" 
              value={tickerSearch}
              onChange={(e) => setTickerSearch(e.target.value.toUpperCase())}
              placeholder="Enter Ticker (e.g. NVDA)"
              style={{ flex: 1, padding: '10px', fontSize: '16px' }}
            />
            <button onClick={handleLookup} disabled={lookingUp}>
              {lookingUp ? '...' : 'Search'}
            </button>
          </div>

          {stockReport && (
            <div style={{ marginTop: '20px', textAlign: 'left', background: '#1a1a1a', padding: '20px', borderRadius: '10px' }}>
              
              {/* HEADER */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0 }}>{stockReport.symbol}</h2>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: stockReport.total_score > 70 ? '#4caf50' : '#ffa726' }}>
                    Score: {stockReport.total_score}
                </div>
              </div>

              {/* FINANCIALS TABLE */}
              <h3>Recent Quarters</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #444', textAlign: 'left' }}>
                    <th style={{ padding: '8px' }}>Date</th>
                    <th style={{ padding: '8px' }}>Revenue</th>
                    <th style={{ padding: '8px' }}>Net Income</th>
                    <th style={{ padding: '8px' }}>EPS</th>
                  </tr>
                </thead>
                <tbody>
                  {stockReport.financials.map((row: any) => (
                    <tr key={row.date} style={{ borderBottom: '1px solid #333' }}>
                      <td style={{ padding: '8px', color: '#888' }}>{new Date(row.date).toLocaleDateString()}</td>
                      <td style={{ padding: '8px' }}>${(row.revenue / 1_000_000).toFixed(1)}M</td>
                      <td style={{ padding: '8px' }}>${(row.net_income / 1_000_000).toFixed(1)}M</td>
                      <td style={{ padding: '8px' }}>{row.eps}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* SURPRISE TABLE */}
              {stockReport.surprises.length > 0 && (
                <>
                    <h3>Earnings Surprises</h3>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        {stockReport.surprises.map((s: any) => (
                            <div key={s.date} style={{ background: '#333', padding: '10px', borderRadius: '5px', textAlign: 'center' }}>
                                <div style={{ fontSize: '12px', color: '#aaa' }}>{new Date(s.date).toLocaleDateString()}</div>
                                
                                {/* FIX: Multiply by 100 and fix to 2 decimals */}
                                <div style={{ fontWeight: 'bold', color: s.surprise_percent > 0 ? '#4caf50' : '#f44336' }}>
                                    {s.surprise_percent > 0 ? '+' : ''}{(s.surprise_percent * 100).toFixed(2)}%
                                </div>
                            </div>
                        ))}
                    </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

    </div>
  )
}

export default App