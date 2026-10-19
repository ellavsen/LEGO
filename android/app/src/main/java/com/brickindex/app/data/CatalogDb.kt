package com.brickindex.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

// Read-only снапшот каталога из assets/catalog.db
// (создаётся scripts/export_catalog_snapshot.py — схемы должны совпадать 1:1)

@Entity(tableName = "catalog_part")
data class CatalogPart(
    @PrimaryKey val part_num: String,
    val name: String,
    val img_url: String?,
)

@Entity(tableName = "catalog_color")
data class CatalogColor(
    @PrimaryKey val id: Int,
    val name: String,
    val rgb_hex: String,
    val is_trans: Int,
)

@Entity(tableName = "part_attr")
data class PartAttr(
    @PrimaryKey val part_num: String,
    val type: String?,
    val hole_count: Int?,
    val axle_hole_count: Int?,
    val has_axle: Int,
    val gear_teeth: Int?,
    val shape: String?,
    val angle_deg: Double?,
    val length_studs: Double?,
)

data class PartWithAttr(
    val part_num: String,
    val name: String,
    val img_url: String?,
    val type: String?,
    val hole_count: Int?,
    val axle_hole_count: Int?,
    val shape: String?,
)

@Dao
interface CatalogDao {
    @Query("SELECT * FROM catalog_part WHERE part_num = :partNum")
    suspend fun part(partNum: String): CatalogPart?

    @Query("SELECT * FROM catalog_color ORDER BY id")
    suspend fun colors(): List<CatalogColor>

    @Query(
        """SELECT p.part_num, p.name, p.img_url, a.type, a.hole_count,
                  a.axle_hole_count, a.shape
           FROM part_attr a JOIN catalog_part p ON p.part_num = a.part_num
           WHERE (:type IS NULL OR a.type = :type)
             AND (:holes < 0 OR a.hole_count = :holes)
             AND (:axleHoles < 0 OR a.axle_hole_count = :axleHoles)
             AND (:shape IS NULL OR a.shape = :shape)
           ORDER BY p.part_num LIMIT 200"""
    )
    suspend fun search(
        type: String?, holes: Int, axleHoles: Int, shape: String?,
    ): List<PartWithAttr>
}

@Database(
    entities = [CatalogPart::class, CatalogColor::class, PartAttr::class],
    version = 1, exportSchema = false,
)
abstract class CatalogDb : RoomDatabase() {
    abstract fun dao(): CatalogDao

    companion object {
        @Volatile private var instance: CatalogDb? = null

        fun get(context: Context): CatalogDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext, CatalogDb::class.java, "catalog.db"
            ).createFromAsset("catalog.db").build().also { instance = it }
        }
    }
}
