package com.brickindex.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.brickindex.app.AppViewModel
import com.brickindex.app.data.CatalogColor
import com.brickindex.app.data.CatalogPart

@Composable
fun CollectionScreen(vm: AppViewModel) {
    val items by vm.user.collection().collectAsState(initial = emptyList())
    var parts by remember { mutableStateOf<Map<String, CatalogPart>>(emptyMap()) }
    var colors by remember { mutableStateOf<Map<Int, CatalogColor>>(emptyMap()) }

    LaunchedEffect(items) {
        colors = vm.catalog.colors().associateBy { it.id }
        parts = items.mapNotNull { vm.catalog.part(it.part_num) }
            .associateBy { it.part_num }
    }

    Column(Modifier.fillMaxSize().padding(8.dp)) {
        Text(
            "Коллекция: ${items.sumOf { it.quantity }} шт. / ${items.size} позиций",
            style = MaterialTheme.typography.titleMedium,
        )
        LazyColumn {
            items(items, key = { it.id }) { item ->
                Card(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Row(
                        Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        AsyncImage(
                            model = parts[item.part_num]?.img_url,
                            contentDescription = null,
                            modifier = Modifier.size(56.dp),
                        )
                        Column(Modifier.weight(1f).padding(start = 8.dp)) {
                            Text(
                                "${item.part_num}  " +
                                    (parts[item.part_num]?.name ?: "")
                            )
                            Text(
                                listOfNotNull(
                                    colors[item.color_id]?.name,
                                    "${item.quantity} шт.",
                                    item.location_tag,
                                ).joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        IconButton(onClick = { vm.deleteItem(item.id) }) {
                            Icon(Icons.Filled.Delete, "удалить")
                        }
                    }
                }
            }
        }
    }
}
