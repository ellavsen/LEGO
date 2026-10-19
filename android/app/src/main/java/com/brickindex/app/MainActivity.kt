package com.brickindex.app

import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.CameraAlt
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.brickindex.app.data.Api
import com.brickindex.app.data.Candidate
import com.brickindex.app.data.CatalogDb
import com.brickindex.app.data.CollectionItem
import com.brickindex.app.data.PendingConfirmation
import com.brickindex.app.data.UserDb
import com.brickindex.app.ui.AboutScreen
import com.brickindex.app.ui.CollectionScreen
import com.brickindex.app.ui.ScanScreen
import com.brickindex.app.ui.SearchScreen
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class AppViewModel(app: Application) : AndroidViewModel(app) {
    val api = Api(app)
    val catalog = CatalogDb.get(app).dao()
    val user = UserDb.get(app).dao()

    /** Подтверждение кандидата: локальная коллекция + очередь /confirm. */
    fun confirm(
        photo: File, candidates: List<Candidate>, chosen: Candidate,
        colorId: Int, qty: Int, location: String?,
    ) = viewModelScope.launch {
        if (user.increment(chosen.partNum, colorId, qty) == 0) {
            user.insert(
                CollectionItem(
                    part_num = chosen.partNum, color_id = colorId,
                    quantity = qty, location_tag = location,
                )
            )
        }
        val json = JSONArray(candidates.map {
            JSONObject(mapOf("part_num" to it.partNum, "score" to it.score))
        }).toString()
        user.enqueue(
            PendingConfirmation(
                photo_path = photo.absolutePath, candidates_json = json,
                chosen_part_num = chosen.partNum, chosen_color_id = colorId,
            )
        )
        flushPending()
    }

    fun deleteItem(id: Long) = viewModelScope.launch { user.delete(id) }

    /** Отправка накопленных подтверждений (few-shot набор на сервере). */
    fun flushPending() = viewModelScope.launch {
        for (p in user.pending()) {
            try {
                val f = File(p.photo_path)
                if (f.exists()) {
                    api.confirm(
                        f, p.candidates_json,
                        p.chosen_part_num, p.chosen_color_id,
                    )
                }
                user.dequeue(p.id)
            } catch (_: Exception) {
                break // нет сети/сервера — досылаем в следующий раз
            }
        }
    }
}

class MainActivity : ComponentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                val nav = rememberNavController()
                val vm: AppViewModel = viewModel()
                vm.flushPending()
                val items = listOf(
                    Triple("scan", "Скан", Icons.Filled.CameraAlt),
                    Triple("collection", "Коллекция", Icons.Filled.List),
                    Triple("search", "Поиск", Icons.Filled.Search),
                    Triple("about", "Инфо", Icons.Filled.Info),
                )
                Scaffold(bottomBar = {
                    NavigationBar {
                        val backStack by nav.currentBackStackEntryAsState()
                        val current = backStack?.destination?.route
                        items.forEach { (route, label, icon) ->
                            NavigationBarItem(
                                selected = current == route,
                                onClick = {
                                    nav.navigate(route) { popUpTo("scan"); launchSingleTop = true }
                                },
                                icon = { Icon(icon, label) },
                                label = { Text(label) },
                            )
                        }
                    }
                }) { padding ->
                    NavHost(
                        nav, startDestination = "scan",
                        modifier = Modifier.padding(padding),
                    ) {
                        composable("scan") { ScanScreen(vm) }
                        composable("collection") { CollectionScreen(vm) }
                        composable("search") { SearchScreen(vm) }
                        composable("about") { AboutScreen(vm) }
                    }
                }
            }
        }
    }
}
