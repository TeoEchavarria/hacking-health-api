#!/bin/bash
# =============================================================================
# MongoDB Verification Queries for Location Sharing Feature
# =============================================================================
#
# Run these queries in MongoDB shell (mongosh) to verify the location
# implementation is working correctly.
#
# Usage:
#   mongosh mongodb://localhost:27017/hacking_health < verify_location.sh
#   OR copy individual queries to MongoDB Compass or mongosh
#
# =============================================================================

echo "=============================================="
echo "VERIFICACIÓN DE UBICACIÓN COMPARTIDA"
echo "=============================================="

# -----------------------------------------------------------------------------
# 1. Verificar que lastLocation existe en documentos de User
# -----------------------------------------------------------------------------
echo ""
echo "1. USUARIOS CON lastLocation CONFIGURADO:"
echo "   (Debe mostrar usuarios con ubicación embebida en formato GeoJSON)"

db.users.find(
  { "lastLocation.coordinates": { $exists: true } },
  { name: 1, email: 1, lastLocation: 1, sharingLocation: 1 }
).limit(5).pretty()

# -----------------------------------------------------------------------------
# 2. Verificar formato GeoJSON correcto
# -----------------------------------------------------------------------------
echo ""
echo "2. VERIFICAR FORMATO GEOJSON:"
echo "   coordinates[0] debe ser LONGITUDE (-180 a 180)"
echo "   coordinates[1] debe ser LATITUDE (-90 a 90)"

db.users.aggregate([
  { $match: { "lastLocation.coordinates": { $exists: true } } },
  { $project: {
      name: 1,
      longitude: { $arrayElemAt: ["$lastLocation.coordinates", 0] },
      latitude: { $arrayElemAt: ["$lastLocation.coordinates", 1] },
      accuracy: "$lastLocation.accuracy",
      updatedAt: "$lastLocation.updatedAt",
      type: "$lastLocation.type"
  }},
  { $limit: 5 }
])

# -----------------------------------------------------------------------------
# 3. Verificar índice 2dsphere
# -----------------------------------------------------------------------------
echo ""
echo "3. ÍNDICES EN COLECCIÓN USERS:"
echo "   Debe existir un índice '2dsphere' en lastLocation"

db.users.getIndexes()

# -----------------------------------------------------------------------------
# 4. Contar documentos en colección locations (historial)
# -----------------------------------------------------------------------------
echo ""
echo "4. CONTEO DE HISTORIAL DE UBICACIONES:"
echo "   Estos documentos expiran automáticamente después de 7 días"

db.locations.countDocuments()

# Mostrar algunos documentos recientes
echo ""
echo "   Documentos más recientes:"
db.locations.find().sort({ createdAt: -1 }).limit(3).pretty()

# -----------------------------------------------------------------------------
# 5. Verificar que NO hay crecimiento excesivo
# -----------------------------------------------------------------------------
echo ""
echo "5. VERIFICAR CRECIMIENTO CONTROLADO:"
echo "   Usuarios con lastLocation vs documentos en locations collection"

var usersWithLocation = db.users.countDocuments({ "lastLocation.coordinates": { $exists: true } })
var locationDocs = db.locations.countDocuments()
var today = new Date()
var sevenDaysAgo = new Date(today.getTime() - (7 * 24 * 60 * 60 * 1000))
var recentLocationDocs = db.locations.countDocuments({ createdAt: { $gte: sevenDaysAgo } })

print("   - Usuarios con lastLocation: " + usersWithLocation)
print("   - Total documentos en locations: " + locationDocs)
print("   - Documentos en últimos 7 días: " + recentLocationDocs)
print("   - NOTA: locations collection es solo historial con TTL de 7 días")

# -----------------------------------------------------------------------------
# 6. Verificar ubicaciones stale (> 15 minutos)
# -----------------------------------------------------------------------------
echo ""
echo "6. UBICACIONES STALE (> 15 minutos):"

var fifteenMinutesAgo = new Date(Date.now() - (15 * 60 * 1000))

db.users.find(
  { 
    "lastLocation.updatedAt": { $lte: fifteenMinutesAgo },
    "lastLocation.coordinates": { $exists: true }
  },
  { name: 1, "lastLocation.updatedAt": 1 }
).limit(5).pretty()

# -----------------------------------------------------------------------------
# 7. Verificar pairings activos con ubicación disponible
# -----------------------------------------------------------------------------
echo ""
echo "7. PAIRINGS ACTIVOS CON UBICACIÓN:"

db.pairings.aggregate([
  { $match: { status: "active" } },
  { $lookup: {
      from: "users",
      let: { patientId: { $toObjectId: "$patientId" } },
      pipeline: [
        { $match: { $expr: { $eq: ["$_id", "$$patientId"] } } },
        { $project: { name: 1, lastLocation: 1, sharingLocation: 1 } }
      ],
      as: "patient"
  }},
  { $lookup: {
      from: "users",
      let: { caregiverId: { $toObjectId: "$caregiverId" } },
      pipeline: [
        { $match: { $expr: { $eq: ["$_id", "$$caregiverId"] } } },
        { $project: { name: 1, lastLocation: 1, sharingLocation: 1 } }
      ],
      as: "caregiver"
  }},
  { $project: {
      patientName: "$patientName",
      caregiverName: "$caregiverName",
      patientHasLocation: { $cond: [{ $gt: [{ $size: { $ifNull: [{ $arrayElemAt: ["$patient.lastLocation.coordinates", 0] }, []] } }, 0] }, true, false] },
      caregiverHasLocation: { $cond: [{ $gt: [{ $size: { $ifNull: [{ $arrayElemAt: ["$caregiver.lastLocation.coordinates", 0] }, []] } }, 0] }, true, false] },
      patientSharingEnabled: { $ifNull: [{ $arrayElemAt: ["$patient.sharingLocation", 0] }, true] },
      caregiverSharingEnabled: { $ifNull: [{ $arrayElemAt: ["$caregiver.sharingLocation", 0] }, true] }
  }},
  { $limit: 5 }
])

echo ""
echo "=============================================="
echo "VERIFICACIÓN COMPLETADA"
echo "=============================================="
