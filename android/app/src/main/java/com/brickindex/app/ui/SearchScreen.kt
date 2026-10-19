package com.brickindex.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.brickindex.app.AppViewModel
import com.brickindex.app.data.PartWithAttr
import kotlinx.coroutines.launch

private val TYPES = listOf(
    null, "beam", "beam_thin", "brick", "axle", "pin", "gear",
    "connector", "panel", "bush", "other",
)
private val SHAPES = listOf(null, "straight", "L", "T", "bent", "angled", "round")

@Composable
private fun Picker(
    label: String, options: List<String?>, value: String?,
    onPick: (String?) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    OutlinedButton(onClick = { open = true }) {
        Text("$label: ${value ?: "любой"}")
    }
    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
        options.forEach { opt ->
            DropdownMenuItem(
                text = { Text(opt ?: "любой") },
                onClick = { onPick(opt); open = false },
            )
        }
    }
}

@Composable
fun SearchScreen(vm: AppViewModel) {
    var type by remember { mutableStateOf<String?>(null) }
    var shape by remember { mutableStateOf<String?>(null) }
    var holes by remember { mutableStateOf("") }
    var axleHoles by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<PartWithAttr>>(emptyList()) }
    var owned by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }
    var searched by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize().padding(8.dp)) {
        Row {
            Picker("Тип", TYPES, type) { type = it }
            Picker("Форма", SHAPES, shape) { shape = it }
        }
        Row {
            OutlinedTextField(
                holes, { holes = it }, label = { Text("Отверстий") },
                modifier = Modifier.weight(1f).padding(end = 4.dp),
            )
            OutlinedTextField(
                axleHoles, { axleHoles = it }, label = { Text("Крестовых") },
                modifier = Modifier.weight(1f),
            )
        }
        Button(
            onClick = {
                scope.launch {
                    results = vm.catalog.search(
                        type, holes.toIntOrNull() ?: -1,
                        axleHoles.toIntOrNull() ?: -1, shape,
                    )
                    owned = results.associate {
                        it.part_num to vm.user.quantityOf(it.part_num)
                    }
                    searched = true
                }
            },
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        ) { Text("Найти") }

        if (searched) Text("Найдено: ${results.size}")
        LazyColumn {
            items(results, key = { it.part_num }) { r ->
                Card(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Row(
                        Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        AsyncImage(
                            model = r.img_url, contentDescription = null,
                            modifier = Modifier.size(56.dp),
                        )
                        Column(Modifier.padding(start = 8.dp)) {
                            Text("${r.part_num}  ${r.name}")
                            val qty = owned[r.part_num] ?: 0
                            Text(
                                listOfNotNull(
                                    r.type, r.shape,
                                    r.hole_count?.let { "$it отв." },
                                    r.axle_hole_count?.let { "$it крест." },
                                    if (qty > 0) "у вас: $qty шт." else "нет в коллекции",
                                ).joinToString(" · ")
                            )
                        }
                    }
                }
            }
        }
    }
}
