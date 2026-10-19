package com.brickindex.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import coil.compose.AsyncImage
import com.brickindex.app.AppViewModel
import com.brickindex.app.data.Candidate
import kotlinx.coroutines.launch
import java.io.File

@Composable
fun ScanScreen(vm: AppViewModel) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED
        )
    }
    val ask = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted = it }
    LaunchedEffect(Unit) { if (!granted) ask.launch(Manifest.permission.CAMERA) }
    if (!granted) {
        Text("Нужно разрешение камеры", Modifier.padding(24.dp))
        return
    }

    var photo by remember { mutableStateOf<File?>(null) }
    var candidates by remember { mutableStateOf<List<Candidate>?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    if (photo == null) {
        // видоискатель
        val capture = remember { ImageCapture.Builder().build() }
        Column(Modifier.fillMaxSize()) {
            AndroidView(
                factory = { ctx ->
                    PreviewView(ctx).also { view ->
                        val provider = ProcessCameraProvider.getInstance(ctx)
                        provider.addListener({
                            val p = provider.get()
                            val preview = androidx.camera.core.Preview.Builder().build()
                            preview.surfaceProvider = view.surfaceProvider
                            p.unbindAll()
                            p.bindToLifecycle(
                                ctx as androidx.lifecycle.LifecycleOwner,
                                CameraSelector.DEFAULT_BACK_CAMERA,
                                preview, capture,
                            )
                        }, ContextCompat.getMainExecutor(ctx))
                    }
                },
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )
            Text(
                "Одна-несколько деталей на контрастном фоне; белая карточка в кадре улучшит цвет",
                Modifier.padding(8.dp),
            )
            Button(
                onClick = {
                    val f = File.createTempFile("scan", ".jpg", context.cacheDir)
                    capture.takePicture(
                        ImageCapture.OutputFileOptions.Builder(f).build(),
                        ContextCompat.getMainExecutor(context),
                        object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(r: ImageCapture.OutputFileResults) {
                                photo = f
                            }
                            override fun onError(e: ImageCaptureException) {
                                error = e.message
                            }
                        },
                    )
                },
                modifier = Modifier.fillMaxWidth().padding(8.dp),
            ) { Text("Снять") }
        }
    } else {
        // результат идентификации
        LaunchedEffect(photo) {
            busy = true; error = null
            try {
                candidates = vm.api.identify(photo!!)
            } catch (e: Exception) {
                error = e.message
            }
            busy = false
        }
        Column(Modifier.fillMaxSize().padding(8.dp)) {
            when {
                busy -> Row(
                    Modifier.fillMaxWidth().padding(24.dp),
                    horizontalArrangement = Arrangement.Center,
                ) { CircularProgressIndicator() }

                error != null -> Column {
                    Text("Ошибка: $error")
                    Button(onClick = { photo = null }) { Text("Снова") }
                }

                else -> CandidateList(vm, photo!!, candidates.orEmpty()) {
                    photo = null; candidates = null
                }
            }
        }
    }
}

@Composable
private fun CandidateList(
    vm: AppViewModel, photo: File, candidates: List<Candidate>,
    onDone: () -> Unit,
) {
    var chosen by remember { mutableStateOf<Candidate?>(null) }
    val scope = rememberCoroutineScope()

    LazyColumn {
        items(candidates) { c ->
            Card(
                onClick = { chosen = c },
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            ) {
                Row(
                    Modifier.padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    AsyncImage(
                        model = c.imgUrl, contentDescription = null,
                        modifier = Modifier.size(64.dp),
                    )
                    Column(Modifier.padding(start = 8.dp)) {
                        Text("${c.partNum}  ${c.name ?: ""}")
                        c.color?.let {
                            Text(
                                it.colorName +
                                    if (it.needsConfirmation) " (проверьте цвет)" else ""
                            )
                        }
                    }
                }
            }
        }
        item { TextButton(onClick = onDone) { Text("Отмена / новый снимок") } }
    }

    chosen?.let { c ->
        var qty by remember { mutableStateOf("1") }
        var location by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { chosen = null },
            title = { Text("${c.partNum} — в коллекцию") },
            text = {
                Column {
                    OutlinedTextField(
                        qty, { qty = it }, label = { Text("Количество") })
                    OutlinedTextField(
                        location, { location = it },
                        label = { Text("Локация (ящик)") })
                }
            },
            confirmButton = {
                Button(onClick = {
                    vm.confirm(
                        photo, candidates, c,
                        colorId = c.color?.colorId ?: -1,
                        qty = qty.toIntOrNull() ?: 1,
                        location = location.ifBlank { null },
                    )
                    chosen = null
                    onDone()
                }) { Text("Подтвердить") }
            },
            dismissButton = {
                TextButton(onClick = { chosen = null }) { Text("Отмена") }
            },
        )
    }
}
