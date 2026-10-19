package com.brickindex.app.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

// Клиент сервера инференса (FastAPI, LEGO.md §6.1)

data class ColorGuess(
    val colorId: Int, val colorName: String,
    val distance: Double, val needsConfirmation: Boolean,
)

data class Candidate(
    val partNum: String, val score: Double, val name: String?,
    val imgUrl: String?, val color: ColorGuess?,
)

class Api(context: Context) {
    private val prefs = context.getSharedPreferences("api", Context.MODE_PRIVATE)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)  // эмбеддинг на CPU может быть долгим
        .build()

    var baseUrl: String
        get() = prefs.getString("base_url", "http://192.168.1.100:8000")!!
        set(v) = prefs.edit().putString("base_url", v.trimEnd('/')).apply()

    suspend fun identify(photo: File, k: Int = 5): List<Candidate> =
        withContext(Dispatchers.IO) {
            val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart(
                    "file", photo.name,
                    photo.asRequestBody("image/jpeg".toMediaType())
                ).build()
            val req = Request.Builder().url("$baseUrl/identify?k=$k")
                .post(body).build()
            client.newCall(req).execute().use { resp ->
                check(resp.isSuccessful) { "identify: HTTP ${resp.code}" }
                val json = JSONObject(resp.body!!.string())
                val arr = json.getJSONArray("candidates")
                (0 until arr.length()).map { i ->
                    val c = arr.getJSONObject(i)
                    val col = c.optJSONObject("color")
                    Candidate(
                        partNum = c.getString("part_num"),
                        score = c.getDouble("score"),
                        name = c.optString("name").takeIf { it.isNotEmpty() },
                        imgUrl = c.optString("img_url").takeIf { it.isNotEmpty() },
                        color = col?.let {
                            ColorGuess(
                                it.getInt("color_id"),
                                it.getString("color_name"),
                                it.getDouble("distance"),
                                c.optBoolean("color_needs_confirmation"),
                            )
                        },
                    )
                }
            }
        }

    suspend fun confirm(
        photo: File, candidatesJson: String,
        chosenPartNum: String, chosenColorId: Int?,
    ): Unit = withContext(Dispatchers.IO) {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart(
                "file", photo.name,
                photo.asRequestBody("image/jpeg".toMediaType())
            )
            .addFormDataPart("candidates", candidatesJson)
            .addFormDataPart("chosen_part_num", chosenPartNum)
            .apply {
                chosenColorId?.let { addFormDataPart("chosen_color_id", "$it") }
            }
            .build()
        val req = Request.Builder().url("$baseUrl/confirm").post(body).build()
        client.newCall(req).execute().use { resp ->
            check(resp.isSuccessful) { "confirm: HTTP ${resp.code}" }
        }
    }
}
