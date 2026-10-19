package com.brickindex.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

// Локальная коллекция пользователя — источник правды (LEGO.md §6.2/§6.3)

@Entity(tableName = "collection")
data class CollectionItem(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val part_num: String,
    val color_id: Int,
    val quantity: Int,
    val location_tag: String?,
    val added_at: Long = System.currentTimeMillis(),
    val verified: Boolean = true,
)

// очередь подтверждений для POST /confirm (few-shot набор на сервере)
@Entity(tableName = "pending_confirmation")
data class PendingConfirmation(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val photo_path: String,
    val candidates_json: String,
    val chosen_part_num: String,
    val chosen_color_id: Int?,
)

@Dao
interface UserDao {
    @Query("SELECT * FROM collection ORDER BY added_at DESC")
    fun collection(): Flow<List<CollectionItem>>

    @Query(
        """UPDATE collection SET quantity = quantity + :qty
           WHERE part_num = :partNum AND color_id = :colorId"""
    )
    suspend fun increment(partNum: String, colorId: Int, qty: Int): Int

    @Insert
    suspend fun insert(item: CollectionItem)

    @Query("DELETE FROM collection WHERE id = :id")
    suspend fun delete(id: Long)

    @Query("SELECT coalesce(sum(quantity), 0) FROM collection WHERE part_num = :partNum")
    suspend fun quantityOf(partNum: String): Int

    @Insert
    suspend fun enqueue(p: PendingConfirmation)

    @Query("SELECT * FROM pending_confirmation ORDER BY id LIMIT 20")
    suspend fun pending(): List<PendingConfirmation>

    @Query("DELETE FROM pending_confirmation WHERE id = :id")
    suspend fun dequeue(id: Long)
}

@Database(
    entities = [CollectionItem::class, PendingConfirmation::class],
    version = 1, exportSchema = false,
)
abstract class UserDb : RoomDatabase() {
    abstract fun dao(): UserDao

    companion object {
        @Volatile private var instance: UserDb? = null

        fun get(context: Context): UserDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext, UserDb::class.java, "user.db"
            ).build().also { instance = it }
        }
    }
}
