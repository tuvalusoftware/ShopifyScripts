# Health Check - GET /health
curl -X GET http://localhost:3000/health -H "Content-Type: application/json"

# Process Order - POST /api/process-order (Valid Request)
curl -X POST http://localhost:3000/api/process-order -H "Content-Type: application/json" -d '{"orderTaskId":101,"orderConfirmationNumber":"PO-2025-0001","brandName":"MARGESHERWOOD","status":"pending","createdAt":"2025-01-15T10:30:00Z","shipDate":"2025-02-15","shopDomain":"pipe-row.myshopify.com","customerName":"Pipe Row Boutique","customerEmail":"orders@piperow.com","buyerEmail":"buyer@piperow.com","orderDate":"2025-01-10","headline":"Spring 2025 Collection","items":[]}'

# Process Order - POST /api/process-order (Missing Required Fields - Should return 400)
curl -X POST http://localhost:3000/api/process-order -H "Content-Type: application/json" -d '{"orderTaskId":102}'

# Process Order - POST /api/process-order (Invalid JSON - Should return 400)
curl -X POST http://localhost:3000/api/process-order -H "Content-Type: application/json" -d 'invalid json'
